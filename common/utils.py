import os
import oci
from typing import Optional, Dict


class OCIUtils:
    """
    Central utility class for shared reusable logic across the project.
    """

    # -------------------- Path Utilities --------------------
    @staticmethod
    def clean_path(path_string: str) -> str:
        """
        Normalizes a compartment path:
        - Removes extra slashes
        - Treats leading 'root' or '/' as the tenancy level

        Examples:
            'test'          -> 'test'
            '/test'         -> 'test'
            'root/test'     -> 'test'
            'root///odi/x/' -> 'odi/x'
            'root'          -> ''   (means tenancy itself)
            '/'             -> ''   (means tenancy itself)
        """
        # Basic normalization: trim & collapse slashes
        cleaned = '/'.join(filter(None, path_string.strip().split('/')))

        if not cleaned:
            return ""

        parts = cleaned.split('/')

        # If first part is 'root', drop it so path is relative to tenancy
        if parts[0].lower() == "root":
            parts = parts[1:]

        return '/'.join(parts)

    # -------------------- OCI Config Loader --------------------
    @staticmethod
    def get_config(config_file: str, profile_name: Optional[str] = None) -> Dict:
        """
        Reads OCI configuration from file using the given profile.
        Falls back to DEFAULT profile if input is None or empty.

        :param config_file: Path to OCI config file
        :param profile_name: OCI profile name (optional)
        :return: OCI SDK config object
        """

        final_profile = profile_name.strip() if profile_name and profile_name.strip() else "DEFAULT"

        if not config_file or not os.path.exists(config_file):
            raise FileNotFoundError(f"OCI config file not found: {config_file}")

        return oci.config.from_file(
            file_location=config_file,
            profile_name=final_profile
        )
