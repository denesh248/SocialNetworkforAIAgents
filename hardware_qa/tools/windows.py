"""Windows allow-listed inspection tools (fixed PowerShell CIM queries)."""

from hardware_qa.tools.registry import ToolSpec

WINDOWS_TOOLS: dict[str, ToolSpec] = {
    "get_cpu_info": ToolSpec(
        argv=[
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "Get-CimInstance Win32_Processor | "
            "Select-Object Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed | "
            "ConvertTo-Json -Compress",
        ],
    ),
    "get_memory_summary": ToolSpec(
        argv=[
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "Get-CimInstance Win32_OperatingSystem | "
            "Select-Object TotalVisibleMemorySize,FreePhysicalMemory | ConvertTo-Json -Compress",
        ],
    ),
    "get_memory_topology": ToolSpec(
        argv=[
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "Get-CimInstance Win32_PhysicalMemory | "
            "Select-Object BankLabel,Capacity,Speed,Manufacturer,PartNumber | ConvertTo-Json -Compress",
        ],
    ),
    "get_block_devices": ToolSpec(
        argv=[
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "Get-CimInstance Win32_DiskDrive | "
            "Select-Object Model,Size,MediaType,InterfaceType,DeviceID | ConvertTo-Json -Compress",
        ],
    ),
    "get_gpu_info": ToolSpec(
        argv=[
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "Get-CimInstance Win32_VideoController | "
            "Select-Object Name,AdapterRAM,DriverVersion | ConvertTo-Json -Compress",
        ],
    ),
    "get_dmi_system": ToolSpec(
        argv=[
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "$cs = Get-CimInstance Win32_ComputerSystem; "
            "$bb = Get-CimInstance Win32_BaseBoard; "
            "[pscustomobject]@{Manufacturer=$cs.Manufacturer;ProductName=$cs.Model;"
            "BoardName=$bb.Product;BoardVendor=$bb.Manufacturer} | ConvertTo-Json -Compress",
        ],
    ),
    "get_pci_devices": ToolSpec(
        argv=[
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "Get-CimInstance Win32_PnPEntity | Select-Object -First 40 Name,PNPClass | ConvertTo-Json -Compress",
        ],
    ),
}
