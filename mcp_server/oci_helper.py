# oci_helper.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Any
import logging
import time

import oci  # pip install oci
from oci.pagination import list_call_get_all_results

from common.utils import OCIUtils

logger = logging.getLogger(__name__)

@dataclass
class InstanceInfo:
    id: str
    display_name: str
    lifecycle_state: str
    shape: str
    availability_domain: str
    compartment_id: str
    metadata: dict | None = None

# -------------------- Compartment Cache ------------------------
class CompartmentCache:
    def __init__(self):
        self._cache = {}
    def get(self, path):
        return self._cache.get(path)
    def set(self, path, ocid):
        self._cache[path] = ocid

compartment_cache = CompartmentCache()

class OCIHelper:

    def __init__(
        self,
        config_file: str = "/scratch/voggu/oci/OCI-MCP-SmartQueryAI/.oci/config",
        profile: str = "bhaskaro",
    ) -> None:
        self.config = OCIUtils.get_config(config_file, profile)
        self.tenancy_ocid = self.config["tenancy"]

        self.identity_client = oci.identity.IdentityClient(self.config)
        self.compute_client = oci.core.ComputeClient(self.config)
        self.vn_client = oci.core.VirtualNetworkClient(self.config)

        # Simple cache (you can replace with your own)
        self.compartment_cache = {}

    # Valid states we care about (ignore TERMINATED)
    _VALID_STATES = {
        "PROVISIONING",
        "STARTING",
        "RUNNING",
        "STOPPING",
        "STOPPED",
    }

    def get_compartment_ocid(self, comp_name: str) -> str:
        """
        Resolve a compartment OCID by its name.
        `comp_name` can be a simple name ("test") or a path ("root/odi").
        Returns tenancy OCID if empty path.
        """
        cleaned_path = OCIUtils.clean_path(comp_name)
        if not cleaned_path:
            return self.tenancy_ocid

        cached = self.compartment_cache.get(cleaned_path)
        if cached:
            logger.debug(f"CACHE HIT for compartment path: {cleaned_path}")
            return cached

        comp_names = cleaned_path.split("/")
        parent_id = self.tenancy_ocid
        last_ocid = None

        for name in comp_names:
            response = self.identity_client.list_compartments(
                compartment_id=parent_id,
                name=name,
                access_level="ACCESSIBLE",
            )
            compartments = response.data
            found = next((c for c in compartments if c.name == name), None)
            if not found:
                raise RuntimeError(
                    f"Compartment '{name}' not found under parent {parent_id}"
                )
            last_ocid = parent_id = found.id

        self.compartment_cache[cleaned_path] = last_ocid
        return last_ocid

    def get_list_of_instances(
        self,
        compartment_ocid: str,
        only_active: bool = True,
    ) -> List[InstanceInfo]:
        """
        List compute instances in the given compartment.
        Optionally filter to non-terminated (active-ish) states.
        """
        instances: List[InstanceInfo] = []
        page_token: Optional[str] = None

        while True:
            response = self.compute_client.list_instances(
                compartment_id=compartment_ocid,
                page=page_token,
            )

            for inst in response.data:
                if only_active and inst.lifecycle_state not in self._VALID_STATES:
                    continue

                instances.append(
                    InstanceInfo(
                        id=inst.id,
                        display_name=inst.display_name,
                        lifecycle_state=inst.lifecycle_state,
                        shape=inst.shape,
                        availability_domain=inst.availability_domain,
                        compartment_id=inst.compartment_id,
                        metadata=getattr(inst, "metadata", None),
                    )
                )

            if not response.has_next_page:
                break
            page_token = response.next_page

        return instances

    def get_instance_by_name(
        self,
        compartment_ocid: str,
        display_name: str,
        only_active: bool = True,
    ) -> Optional[InstanceInfo]:
        """
        Return the first matching instance with the given display_name in the compartment.
        Returns None if not found.

        This is the 'new style' version of your old get_existing_instance_by_name.
        """
        page_token: Optional[str] = None

        while True:
            response = self.compute_client.list_instances(
                compartment_id=compartment_ocid,
                display_name=display_name,  # server-side filter
                page=page_token,
                sort_by="TIMECREATED",
                sort_order="DESC",                
            )

            for inst in response.data:
                if inst.display_name.lower() != display_name.lower():
                    continue
                if only_active and inst.lifecycle_state not in self._VALID_STATES:
                    continue

                return InstanceInfo(
                    id=inst.id,
                    display_name=inst.display_name,
                    lifecycle_state=inst.lifecycle_state,
                    shape=inst.shape,
                    availability_domain=inst.availability_domain,
                    compartment_id=inst.compartment_id,
                    metadata=getattr(inst, "metadata", None),
                )

            if not response.has_next_page:
                break
            page_token = response.next_page

        return None

    def get_subnet_by_name(self, compartment_ocid: str, subnet_name: str) -> str:
        """
        Resolve subnet OCID by subnet name within a specific compartment.
        """
        if not compartment_ocid:
            raise ValueError("compartment_ocid must not be empty")
        if not subnet_name:
            raise ValueError("subnet_name must not be empty")

        subnets = self.vn_client.list_subnets(
            compartment_id=compartment_ocid,
            display_name=subnet_name
        ).data

        if not subnets:
            raise RuntimeError(
                f"Subnet '{subnet_name}' not found in compartment {compartment_ocid}"
            )

        return subnets[0].id

    def get_available_subnets(self, compartment_ocid: str) -> list[dict]:
        """
        Return all subnets in the given compartment.

        :param compartment_ocid: OCI compartment OCID
        :return: List of subnet metadata dicts
        """
        if not compartment_ocid:
            raise ValueError("compartment_ocid must not be empty")

        subnets = self.vn_client.list_subnets(
            compartment_id=compartment_ocid
        ).data

        if not subnets:
            raise RuntimeError(f"No subnets found in compartment {compartment_ocid}")

        # Return minimal, clean structure for AI + UI
        return [
            {
                "id": s.id,
                "name": s.display_name,
                "cidr": getattr(s, "cidr_block", None),
                "lifecycle_state": getattr(s, "lifecycle_state", None),
                "vcn_id": getattr(s, "vcn_id", None)
            }
            for s in subnets
        ]

    def get_latest_image_by_prefix(self, compartment_ocid: str, image_name_prefix: str) -> dict:
        """
        Get the latest OCI image by name prefix in a compartment.

        :param compartment_ocid: Compartment OCID
        :param image_name_prefix: Image name prefix (e.g. 'ODI', 'MyCustomImage')
        :return: Dict with image details
        """
        if not compartment_ocid:
            raise ValueError("compartment_ocid must not be empty")
        if not image_name_prefix:
            raise ValueError("image_name_prefix must not be empty")

        print("-----------------------------------------------------------")
        print(f"compartment_ocid : {compartment_ocid}")
        print(f"image_name_prefix : {image_name_prefix}")
        images = self.compute_client.list_images(
            compartment_id=compartment_ocid,
            # operating_system="Oracle Linux",
            sort_by="TIMECREATED",
            sort_order="DESC",
            lifecycle_state="AVAILABLE",
        ).data
        print(f"images : {images}")
        # Filter by prefix
        matching_images = [
            img for img in images
            if img.display_name and img.display_name.lower().startswith(image_name_prefix.lower())
        ]
        print(f"matching_images : {matching_images}")

        if not matching_images:
            raise RuntimeError(
                f"No images found with prefix '{image_name_prefix}' in compartment {compartment_ocid}"
            )

        latest = matching_images[0]

        return {
            "id": latest.id,
            "name": latest.display_name,
            "time_created": str(latest.time_created),
            "lifecycle_state": latest.lifecycle_state
        }

    def get_images_by_prefix(self, compartment_ocid: str, image_name_prefix: str) -> list[dict]:
        """
        Get ALL OCI images that match a given name prefix (case-insensitive) in a compartment.
        Uses list_call_get_all_results to handle pagination and retrieve ALL pages.
        
        :param compartment_ocid: Compartment OCID
        :param image_name_prefix: Image name prefix (e.g. 'ODI', 'MyCustomImage')
        :return: List of image detail dicts
        """
        if not compartment_ocid:
            raise ValueError("compartment_ocid must not be empty")
        if not image_name_prefix:
            raise ValueError("image_name_prefix must not be empty")

        print("-----------------------------------------------------------")
        print(f"oci helper -> compartment_ocid : {compartment_ocid}")
        print(f"oci helper -> image_name_prefix : {image_name_prefix}")

        # --- FIX: Use list_call_get_all_results to handle all pages ---
        list_images_response = list_call_get_all_results(
            self.compute_client.list_images,
            compartment_id=compartment_ocid,
            # operating_system="Oracle Linux",  # optional filter if needed
            sort_by="TIMECREATED",
            sort_order="DESC",
            lifecycle_state="AVAILABLE",
        )
        
        # The .data attribute now contains ALL results from ALL pages
        all_images = list_images_response.data 

        print(f"Total images retrieved (all pages): {len(all_images)}")

        # Case-insensitive prefix filter (Your filtering logic remains correct)
        matching_images = [
            img for img in all_images
            if img.display_name
            and img.display_name.lower().startswith(image_name_prefix.lower())
        ]

        print(f"matching_images count after filter: {len(matching_images)}")

        if not matching_images:
            raise RuntimeError(
                f"No images found with prefix '{image_name_prefix}' in compartment {compartment_ocid}"
            )

        # Return clean structured list
        return [
            {
                "id": img.id,
                "name": img.display_name,
                "time_created": str(img.time_created),
                "lifecycle_state": img.lifecycle_state
            }
            for img in matching_images
        ]

    def delete_instance(
            self,
            instance_ocid: str,
            timeout_minutes: int = 10,
            poll_interval: int = 15,
        ) -> dict:
            """
            Terminate (delete) a compute instance and wait for it to reach TERMINATED.

            :param instance_ocid: OCID of the instance to terminate
            :param timeout_minutes: max minutes to wait for TERMINATED
            :param poll_interval: seconds between status checks
            :return: dict with termination result details
            """
            if not instance_ocid:
                raise ValueError("instance_ocid must not be empty")

            print("-----------------------------------------------------------")
            print(f"oci helper -> delete_instance: {instance_ocid}")
            print(f"timeout_minutes: {timeout_minutes}, poll_interval: {poll_interval}")

            try:
                print(f"oci helper -> calling terminate_instance for {instance_ocid}")
                self.compute_client.terminate_instance(instance_ocid)
            except Exception as e:
                print(f"oci helper -> error terminating instance {instance_ocid}: {e}")
                raise

            end_time = time.time() + (timeout_minutes * 60)
            last_state = None

            while time.time() < end_time:
                try:
                    response = self.compute_client.get_instance(instance_ocid)
                    instance = response.data
                    state = instance.lifecycle_state
                    last_state = state
                    print(f"oci helper -> waiting for termination... state: {state}")

                    if state == "TERMINATED":
                        print(f"oci helper -> instance {instance_ocid} successfully terminated.")
                        return {
                            "instance_ocid": instance_ocid,
                            "final_state": state,
                            "terminated": True,
                            "timeout": False,
                            "message": "Instance successfully terminated.",
                        }

                except oci.exceptions.ServiceError as e:
                    # If instance is gone (e.g. 404), treat as terminated
                    if e.status == 404:
                        print(
                            f"oci helper -> get_instance returned 404 for {instance_ocid}, "
                            "treating as terminated."
                        )
                        return {
                            "instance_ocid": instance_ocid,
                            "final_state": "TERMINATED",
                            "terminated": True,
                            "timeout": False,
                            "message": "Instance no longer found (assumed terminated).",
                        }
                    print(f"oci helper -> error polling instance {instance_ocid}: {e}")
                    raise

                time.sleep(poll_interval)

            print(
                f"oci helper -> timeout while waiting for instance {instance_ocid} to terminate. "
                f"Last known state: {last_state}"
            )
            return {
                "instance_ocid": instance_ocid,
                "final_state": last_state or "UNKNOWN",
                "terminated": False,
                "timeout": True,
                "message": "Timeout while waiting for instance to terminate.",
            }


    def create_instance(
        self,
        comp_ocid: str,
        instance_name: str,
        instance_shape: str = "VM.Standard.E2.1.Micro",
        cpu_mem_shape: Optional[str] = None,
        subnet_ocid: Optional[str] = None,
        image_ocid: Optional[str] = None,
        ssh_authorized_keys: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> InstanceInfo:
        """
        Launch an OCI compute instance.

        - If cpu_mem_shape is for flex shapes (e.g. "2OCPU_16GB"), parse & apply to shape config.
        - If subnet_ocid is None, you can choose a default or raise.
        - image_ocid can be auto-resolved to latest Oracle Linux image if not provided.

        Return an InstanceInfo with the launched instance details.
        """
        raise NotImplementedError

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    helper = OCIHelper(
        config_file="/scratch/voggu/oci/OCI-MCP-SmartQueryAI/.oci/config",
        profile="bhaskaro",
    )

    try:
        # 1) Test with simple name
        ocid1 = helper.get_compartment_ocid("test")
        print(f"Compartment 'test' OCID: {ocid1}")

        # 2) Test with path (e.g., root/odi)
        ocid2 = helper.get_compartment_ocid("root/test")
        print(f"Compartment 'root/test' OCID: {ocid2}")

        # 3) Test with empty string (should return tenancy)
        ocid3 = helper.get_compartment_ocid("")
        print(f"Empty path -> tenancy OCID: {ocid3}")

    except Exception as e:
        print(f"Error while testing get_compartment_ocid: {e}")
