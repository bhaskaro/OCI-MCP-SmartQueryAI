import asyncio
import json
from mcp_client.mcp_client_helper import MCPClientWrapper


async def main():
    client = MCPClientWrapper(base_url="http://localhost:8000/mcp")

    # 1. Get compartment OCID
    result = await client.call_tool(
        "get_compartment_ocid",
        {"compartment_name": "root/test"},
    )
    print("Raw MCP result (get_compartment_ocid):", result)

    ocid = result.content[0].text  # plain string
    print("Compartment OCID:", ocid)
    compartment_ocid = ocid

    # 2. List instances
    try:
        instances_result = await client.call_tool(
            "list_instances",
            {"compartment_ocid": compartment_ocid},
        )

        print("\nInstances (raw MCP result):")
        print(instances_result)

        # Prefer structuredContent if available
        instances = None

        if getattr(instances_result, "structuredContent", None):
            # e.g. {'result': [ {...}, {...} ]}
            sc = instances_result.structuredContent
            instances = sc.get("result", None)
        else:
            # Fallback: parse from text JSON
            raw_instances_text = instances_result.content[0].text
            instances = json.loads(raw_instances_text)

        # If still wrapped one level, unwrap
        if isinstance(instances, dict) and "result" in instances:
            instances = instances["result"]

        print("\nParsed Instances:")
        if not instances:
            print("No instances found.")
        else:
            for inst in instances:
                print(f"- {inst['display_name']} | {inst['lifecycle_state']} | {inst['shape']}")
    except Exception as e:
        print("Error in list_instances:", e)

    # 3. Get instance by name
    try:
        instance_name = "AUTOTEST"  # change to your actual VM name

        instance_result = await client.call_tool(
            "get_instance_by_name",
            {
                "compartment_ocid": compartment_ocid,
                "display_name": instance_name,
            },
        )

        print("\nSingle Instance (raw MCP result):")
        print(instance_result)

        instance = None

        if getattr(instance_result, "structuredContent", None):
            sc = instance_result.structuredContent
            instance = sc.get("result", None)
        else:
            raw_instance_text = instance_result.content[0].text
            instance = json.loads(raw_instance_text)

        print("\nFound Instance:" if instance else f"No instance found with name: {instance_name}")

        if instance:
            print(f"Name : {instance['display_name']}")
            print(f"OCID : {instance['id']}")
            print(f"State: {instance['lifecycle_state']}")
            print(f"Shape: {instance['shape']}")
    except Exception as e:
        print("Error in get_instance_by_name:", e)


if __name__ == "__main__":
    asyncio.run(main())
