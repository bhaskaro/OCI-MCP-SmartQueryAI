# mcp_oci_server.py
from __future__ import annotations

import asyncio
from typing import Any, Optional, List

from mcp.server.fastmcp import FastMCP  # pip install "mcp[cli]"
from mcp_server.oci_helper import OCIHelper, InstanceInfo

from mcp.server.fastmcp import FastMCP

# Stateless + JSON is recommended for streamable HTTP :contentReference[oaicite:0]{index=0}
mcp = FastMCP(
    "oci-compute",
    stateless_http=True,
    json_response=True,
)

# oci_helper = OCIHelper()  # uses default config_file + profile from __init__
oci_helper = OCIHelper(
    config_file="/scratch/voggu/oci/OCI-MCP-SmartQueryAI/.oci/config",
    profile="bhaskaro",
)

@mcp.tool()
def get_compartment_ocid(compartment_name: str) -> str:
    """
    Return the OCID of a compartment by name or path (e.g. "test" or "root/test").
    """
    return oci_helper.get_compartment_ocid(compartment_name)


@mcp.tool()
def list_instances(compartment_ocid: str) -> list[dict[str, Any]]:
    """
    List compute instances in the given compartment.
    Returns a JSON-serializable list of instance metadata.
    """
    instances: List[InstanceInfo] = oci_helper.get_list_of_instances(compartment_ocid)

    return [
        {
            "id": i.id,
            "display_name": i.display_name,
            "lifecycle_state": i.lifecycle_state,
            "shape": i.shape,
            "availability_domain": i.availability_domain,
            "compartment_id": i.compartment_id,
            "metadata": i.metadata or {},
        }
        for i in instances
    ]


@mcp.tool()
def get_instance_by_name(
    compartment_ocid: str,
    display_name: str,
) -> Optional[dict[str, Any]]:
    """
    Get a single compute instance in the given compartment by its display name.
    Returns a JSON-serializable dict or null if not found.
    """
    inst: Optional[InstanceInfo] = oci_helper.get_instance_by_name(
        compartment_ocid,
        display_name,
    )

    if inst is None:
        return None

    return {
        "id": inst.id,
        "display_name": inst.display_name,
        "lifecycle_state": inst.lifecycle_state,
        "shape": inst.shape,
        "availability_domain": inst.availability_domain,
        "compartment_id": inst.compartment_id,
        "metadata": inst.metadata or {},
    }


@mcp.tool()
def get_subnet_by_name(compartment_ocid: str, subnet_name: str) -> str:
    """
    Get subnet OCID by subnet display name within a compartment.
    """
    return oci_helper.get_subnet_by_name(compartment_ocid, subnet_name)

@mcp.tool()
def get_available_subnets(compartment_ocid: str) -> list:
    """
    Get ALL available subnets in a given compartment.
    """
    return oci_helper.get_available_subnets(compartment_ocid)

@mcp.tool()
def get_latest_image_by_prefix(compartment_ocid: str, image_name_prefix: str) -> dict:
    """
    Get the latest (most recently created) OCI image whose display name
    starts with the given prefix (case-insensitive) in the specified compartment.
    """
    latest = oci_helper.get_latest_image_by_prefix(compartment_ocid, image_name_prefix)
    # Wrap in result for consistency
    return {"result": latest}


@mcp.tool()
def get_images_by_prefix(compartment_ocid: str, image_name_prefix: str) -> dict:
    """
    Get ALL OCI images whose display name starts with the given prefix
    (case-insensitive) in the specified compartment.
    """
    images = oci_helper.get_images_by_prefix(compartment_ocid, image_name_prefix)
    print(f"mcp server -> images retrieved : {len(images)}")
    # IMPORTANT: return ALL images under a 'result' key
    return {"result": images}

@mcp.tool()
def delete_instance(
    instance_ocid: str,
    timeout_minutes: int = 10,
    poll_interval: int = 15,
) -> dict:
    """
    Terminate (delete) a compute instance by OCID.

    Returns:
      {
        "result": {
          "instance_ocid": "...",
          "final_state": "...",
          "terminated": true/false,
          "timeout": true/false,
          "message": "..."
        }
      }
    """
    result = oci_helper.delete_instance(
        instance_ocid=instance_ocid,
        timeout_minutes=timeout_minutes,
        poll_interval=poll_interval,
    )
    print(
        f"mcp server -> delete_instance: {instance_ocid}, "
        f"terminated={result.get('terminated')}, final_state={result.get('final_state')}"
    )
    return {"result": result}

@mcp.tool()
def create_compute_instance(
    compartment_name: str,
    instance_name: str,
    instance_shape: str = "VM.Standard1.1",
    cpu_mem_shape: Optional[str] = None,
    subnet_name: Optional[str] = None,
) -> dict[str, Any]:
    """
    High-level tool for 'create compute instance in compartment X with name Y'.
    - Resolves compartment OCID from compartment_name.
    - Resolves or auto-selects subnet in that compartment.
    - Launches the instance and returns summary.
    """
    comp_ocid = oci_helper.get_compartment_ocid(compartment_name)
    subnet_ocid = oci_helper.get_available_subnet(comp_ocid, subnet_name=subnet_name)

    inst: InstanceInfo = oci_helper.create_instance(
        comp_ocid=comp_ocid,
        instance_name=instance_name,
        instance_shape=instance_shape,
        cpu_mem_shape=cpu_mem_shape,
        subnet_ocid=subnet_ocid,
    )

    return {
        "id": inst.id,
        "display_name": inst.display_name,
        "lifecycle_state": inst.lifecycle_state,
        "shape": inst.shape,
        "availability_domain": inst.availability_domain,
        "compartment_id": inst.compartment_id,
        "metadata": inst.metadata or {},
    }


async def main() -> None:
    """
    Run MCP server over stdio; you can also adapt to Streamable HTTP later.
    """
    await mcp.run()


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
