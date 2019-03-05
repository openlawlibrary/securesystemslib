#!/usr/bin/env python

"""
<Program Name>
  test_gpg.py

<Author>
  Santiago Torres-Arias <santiago@nyu.edu>
  Lukas Puehringer <lukas.puehringer@nyu.edu>

<Started>
  Nov 15, 2017

<Copyright>
  See LICENSE for licensing information.

<Purpose>
  Test gpg/pgp-related functions.

"""

import os
import shutil
import tempfile
import unittest

import cryptography.hazmat.backends as backends
import cryptography.hazmat.primitives.serialization as serialization
from six import string_types

import securesystemslib.exceptions
import securesystemslib.formats
from securesystemslib.gpg.common import parse_pubkey_payload
from securesystemslib.gpg.dsa import create_pubkey as dsa_create_pubkey
from securesystemslib.gpg.functions import (gpg_export_pubkey, gpg_sign_object,
                                            gpg_verify_signature)
from securesystemslib.gpg.rsa import create_pubkey as rsa_create_pubkey
from securesystemslib.gpg.util import get_version, is_version_fully_supported


@unittest.skipIf(os.getenv("TEST_SKIP_GPG"), "gpg not found")
class TestUtil(unittest.TestCase):
  """Test util functions. """
  def test_version_utils_return_types(self):
    """Run dummy tests for coverage. """
    self.assertTrue(isinstance(get_version(), string_types))
    self.assertTrue(isinstance(is_version_fully_supported(), bool))

@unittest.skipIf(os.getenv("TEST_SKIP_GPG"), "gpg not found")
class TestCommon(unittest.TestCase):
  """Test common functions of the securesystemslib.gpg module. """
  def test_parse_empty_pubkey_payload(self):
    """Test that passing nothing to parse_pubkey_payload raises ValueError. """
    with self.assertRaises(ValueError):
      parse_pubkey_payload(None)


@unittest.skipIf(os.getenv("TEST_SKIP_GPG"), "gpg not found")
class TestGPGRSA(unittest.TestCase):
  """Test signature creation, verification and key export from the gpg
  module"""
  default_keyid = "8465A1E2E0FB2B40ADB2478E18FB3F537E0C8A17"
  signing_subkey_keyid = "C5A0ABE6EC19D0D65F85E2C39BE9DF5131D924E9"
  encryption_subkey_keyid = "6A112FD3390B2E53AFC2E57F8FC8E12099AECEEA"
  unsupported_subkey_keyid = "611A9B648E16F54E8A7FAD5DA51E8CDF3B06524F"

  @classmethod
  def setUpClass(self):
    # Create directory to run the tests without having everything blow up
    self.working_dir = os.getcwd()

    # Find demo files
    gpg_keyring_path = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), "data/gpg_keyrings", "rsa")

    self.test_dir = os.path.realpath(tempfile.mkdtemp())
    self.gnupg_home = os.path.join(self.test_dir, "rsa")
    shutil.copytree(gpg_keyring_path, self.gnupg_home)
    os.chdir(self.test_dir)


  @classmethod
  def tearDownClass(self):
    """Change back to initial working dir and remove temp test directory. """
    os.chdir(self.working_dir)
    shutil.rmtree(self.test_dir)


  def test_gpg_export_pubkey(self):
    """ export a public key and make sure the parameters are the right ones:

      since there's very little we can do to check rsa key parameters are right
      we pre-exported the public key to an ssh key, which we can load with
      cryptography for the sake of comparison """

    # export our gpg key, using our functions
    key_data = gpg_export_pubkey(self.default_keyid, homedir=self.gnupg_home)
    our_exported_key = rsa_create_pubkey(key_data)

    # load the equivalent ssh key, and make sure that we get the same RSA key
    # parameters
    ssh_key_basename = "{}.ssh".format(self.default_keyid)
    ssh_key_path = os.path.join(self.gnupg_home, ssh_key_basename)
    with open(ssh_key_path, "rb") as fp:
      keydata = fp.read()

    ssh_key = serialization.load_ssh_public_key(keydata,
        backends.default_backend())

    self.assertEquals(ssh_key.public_numbers().n,
        our_exported_key.public_numbers().n)
    self.assertEquals(ssh_key.public_numbers().e,
        our_exported_key.public_numbers().e)

    subkey_keyids = list(key_data["subkeys"].keys())
    # We export the whole master key bundle which must contain the subkeys
    self.assertTrue(self.signing_subkey_keyid.lower() in subkey_keyids)
    # Currently we do not exclude encryption subkeys
    self.assertTrue(self.encryption_subkey_keyid.lower() in subkey_keyids)
    # However we do exclude subkeys, whose algorithm we do not support
    self.assertFalse(self.unsupported_subkey_keyid.lower() in subkey_keyids)

    # When passing the subkey keyid we also export the whole keybundle
    key_data2 = gpg_export_pubkey(self.signing_subkey_keyid,
        homedir=self.gnupg_home)
    self.assertDictEqual(key_data, key_data2)


  def test_gpg_export_pubkey_invalid_keyid(self):
    """Test that exception is raised when keyid argument is not valid. """
    with self.assertRaises(ValueError):
      gpg_export_pubkey("_", homedir=self.gnupg_home)


  def test_gpg_export_pubkey_key_not_found(self):
    """Test that exception is raised when keyid argument is not valid. """
    with self.assertRaises(securesystemslib.gpg.exceptions.KeyNotFoundError):
      gpg_export_pubkey("abc", homedir=self.gnupg_home)


  def test_gpg_sign_and_verify_object_with_default_key(self):
    """Create a signature using the default key on the keyring """

    test_data = b'test_data'
    wrong_data = b'something malicious'

    signature = gpg_sign_object(test_data, homedir=self.gnupg_home)
    key_data = gpg_export_pubkey(self.default_keyid, homedir=self.gnupg_home)

    self.assertTrue(gpg_verify_signature(signature, key_data, test_data))
    self.assertFalse(gpg_verify_signature(signature, key_data, wrong_data))



  def test_gpg_sign_and_verify_object(self):
    """Create a signature using a specific key on the keyring """

    test_data = b'test_data'
    wrong_data = b'something malicious'

    signature = gpg_sign_object(test_data, keyid=self.default_keyid,
        homedir=self.gnupg_home)
    key_data = gpg_export_pubkey(self.default_keyid, homedir=self.gnupg_home)
    self.assertTrue(gpg_verify_signature(signature, key_data, test_data))
    self.assertFalse(gpg_verify_signature(signature, key_data, wrong_data))


  def test_gpg_sign_and_verify_object_default_keyring(self):
    """Sign/verify using keyring from envvar. """

    test_data = b'test_data'

    gnupg_home_backup = os.environ.get("GNUPGHOME")
    os.environ["GNUPGHOME"] = self.gnupg_home

    signature = gpg_sign_object(test_data, keyid=self.default_keyid)
    key_data = gpg_export_pubkey(self.default_keyid)
    self.assertTrue(gpg_verify_signature(signature, key_data, test_data))

    # Reset GNUPGHOME
    if gnupg_home_backup:
      os.environ["GNUPGHOME"] = gnupg_home_backup
    else:
      del os.environ["GNUPGHOME"]


@unittest.skipIf(os.getenv("TEST_SKIP_GPG"), "gpg not found")
class TestGPGDSA(unittest.TestCase):
  """ Test signature creation, verification and key export from the gpg
  module """

  default_keyid = "C242A830DAAF1C2BEF604A9EF033A3A3E267B3B1"

  @classmethod
  def setUpClass(self):
    # Create directory to run the tests without having everything blow up
    self.working_dir = os.getcwd()
    self.test_dir = os.path.realpath(tempfile.mkdtemp())
    self.gnupg_home = os.path.join(self.test_dir, "dsa")

    # Find keyrings
    keyrings = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), "data/gpg_keyrings", "dsa")

    shutil.copytree(keyrings, self.gnupg_home)
    os.chdir(self.test_dir)

  @classmethod
  def tearDownClass(self):
    """Change back to initial working dir and remove temp test directory. """
    os.chdir(self.working_dir)
    shutil.rmtree(self.test_dir)

  def test_gpg_export_pubkey(self):
    """ export a public key and make sure the parameters are the right ones:

      since there's very little we can do to check rsa key parameters are right
      we pre-exported the public key to an ssh key, which we can load with
      cryptography for the sake of comparison """

    # export our gpg key, using our functions
    key_data = gpg_export_pubkey(self.default_keyid, homedir=self.gnupg_home)
    our_exported_key = dsa_create_pubkey(key_data)

    # load the equivalent ssh key, and make sure that we get the same RSA key
    # parameters
    ssh_key_basename = "{}.ssh".format(self.default_keyid)
    ssh_key_path = os.path.join(self.gnupg_home, ssh_key_basename)
    with open(ssh_key_path, "rb") as fp:
      keydata = fp.read()

    ssh_key = serialization.load_ssh_public_key(keydata,
        backends.default_backend())

    self.assertEquals(ssh_key.public_numbers().y,
        our_exported_key.public_numbers().y)
    self.assertEquals(ssh_key.public_numbers().parameter_numbers.g,
        our_exported_key.public_numbers().parameter_numbers.g)
    self.assertEquals(ssh_key.public_numbers().parameter_numbers.q,
        our_exported_key.public_numbers().parameter_numbers.q)
    self.assertEquals(ssh_key.public_numbers().parameter_numbers.p,
        our_exported_key.public_numbers().parameter_numbers.p)

  def test_gpg_sign_and_verify_object_with_default_key(self):
    """Create a signature using the default key on the keyring """

    test_data = b'test_data'
    wrong_data = b'something malicious'

    signature = gpg_sign_object(test_data, homedir=self.gnupg_home)
    key_data = gpg_export_pubkey(self.default_keyid, homedir=self.gnupg_home)

    self.assertTrue(gpg_verify_signature(signature, key_data, test_data))
    self.assertFalse(gpg_verify_signature(signature, key_data, wrong_data))


  def test_gpg_sign_and_verify_object(self):
    """Create a signature using a specific key on the keyring """

    test_data = b'test_data'
    wrong_data = b'something malicious'

    signature = gpg_sign_object(test_data, keyid=self.default_keyid,
        homedir=self.gnupg_home)
    key_data = gpg_export_pubkey(self.default_keyid, homedir=self.gnupg_home)

    self.assertTrue(gpg_verify_signature(signature, key_data, test_data))
    self.assertFalse(gpg_verify_signature(signature, key_data, wrong_data))


if __name__ == "__main__":
  unittest.main()
