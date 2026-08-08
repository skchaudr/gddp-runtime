import os

class VaultDoctor:
    """
    A foundational doctor service to scan and check Obsidian vault structures.
    """
    def scan_vault(self, vault_path: str) -> list[dict]:
        """
        Walks the directory tree of the vault and returns a list of file metadata dicts.
        Correctly ignores .obsidian/ and other hidden/system system directories.
        """
        metadata_list = []
        if not os.path.exists(vault_path):
            raise FileNotFoundError(f"Vault path does not exist: {vault_path}")

        for root, dirs, files in os.walk(vault_path):
            # Prune .obsidian and .git directories in-place so os.walk ignores them
            dirs[:] = [d for d in dirs if d not in {'.obsidian', '.git'}]

            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, vault_path)

                # Double-check that we are not accidentally processing hidden/system files
                path_parts = rel_path.split(os.sep)
                if any(part in {'.obsidian', '.git'} for part in path_parts):
                    continue

                try:
                    stat_info = os.stat(full_path)
                    _, ext = os.path.splitext(file)
                    metadata_list.append({
                        "path": rel_path,
                        "size_bytes": stat_info.st_size,
                        "extension": ext.lower(),
                        "modified_at": stat_info.st_mtime
                    })
                except OSError:
                    # Handle permission errors or deleted files during walk
                    continue

        return metadata_list
