import os
import unittest
from src.doctor import VaultDoctor

class TestVaultDoctor(unittest.TestCase):
    def setUp(self):
        # We use the existing mock vault at vault_doctor/mock_vault/ as fixture
        self.mock_vault_path = "vault_doctor/mock_vault"
        self.doctor = VaultDoctor()

    def test_scan_vault_returns_list(self):
        """
        Verify that scan_vault returns a list of dictionaries.
        """
        results = self.doctor.scan_vault(self.mock_vault_path)
        self.assertIsInstance(results, list)
        self.assertTrue(len(results) > 0)

    def test_scan_vault_metadata_structure(self):
        """
        Verify that each metadata dict contains at minimum: path, size_bytes, extension, modified_at.
        """
        results = self.doctor.scan_vault(self.mock_vault_path)
        required_keys = {"path", "size_bytes", "extension", "modified_at"}
        for item in results:
            self.assertIsInstance(item, dict)
            for key in required_keys:
                self.assertIn(key, item, f"Missing key '{key}' in metadata dict: {item}")
            self.assertIsInstance(item["path"], str)
            self.assertIsInstance(item["size_bytes"], int)
            self.assertIsInstance(item["extension"], str)
            self.assertIsInstance(item["modified_at"], (int, float))

    def test_scan_vault_ignores_obsidian(self):
        """
        Verify that scan_vault correctly ignores .obsidian/ system files.
        """
        results = self.doctor.scan_vault(self.mock_vault_path)
        for item in results:
            path_parts = item["path"].split(os.sep)
            self.assertNotIn(".obsidian", path_parts, f"Found .obsidian in scanned path: {item['path']}")

    def test_scan_vault_ignores_git(self):
        """
        Verify that scan_vault correctly ignores .git/ system files.
        """
        results = self.doctor.scan_vault(self.mock_vault_path)
        for item in results:
            path_parts = item["path"].split(os.sep)
            self.assertNotIn(".git", path_parts, f"Found .git in scanned path: {item['path']}")

    def test_scan_vault_file_count(self):
        """
        Verify the count of discovered normal files in our mock vault.
        Expected files:
        1. Inbox/welcome.md
        2. Inbox/todo.md
        3. Archive/old_note.md
        4. root_note.md
        """
        results = self.doctor.scan_vault(self.mock_vault_path)
        expected_paths = {
            "Inbox/welcome.md",
            "Inbox/todo.md",
            "Archive/old_note.md",
            "root_note.md"
        }
        actual_paths = {item["path"] for item in results}
        self.assertEqual(actual_paths, expected_paths)

if __name__ == "__main__":
    unittest.main()
