from pydantic import BaseModel


class GPUInfo(BaseModel):
    gpu_id: int
    name: str
    driver_version: str
    pci_bus_id: str
    gpu_utilization: int
    graphics_clock_mhz: int
    mem_utilization: int
    mem_clock_mhz: int
    memory_total_mib: float
    memory_used_mib: float
    memory_free_mib: float
    temperature: int
    fan_speed: int
    power_usage_mw: int
    power_limit_mw: int


def get_gpu_info() -> list[GPUInfo]:  # Added return type hint
    """
    Retrieves and prints information about installed NVIDIA GPUs using pynvml,
    returning a list of Pydantic GPUInfo objects.
    """
    gpu_info_list: list[GPUInfo] = []
    nvml_initialized = False  # Track if nvmlInit succeeded

    try:
        import pynvml
    except ImportError:
        return []

    try:
        pynvml.nvmlInit()
        nvml_initialized = True

        driver_version_bytes = pynvml.nvmlSystemGetDriverVersion()
        driver_version = (
            driver_version_bytes.decode("utf-8")
            if isinstance(driver_version_bytes, bytes)
            else driver_version_bytes
        )

        device_count = pynvml.nvmlDeviceGetCount()

        if device_count == 0:
            return []

        for i in range(device_count):
            temperature = -1
            fan_speed = -1
            power_usage_mw = -1
            power_limit_mw = -1
            gpu_utilization = -1
            mem_utilization = -1
            graphics_clock_mhz = -1
            mem_clock_mhz = -1
            device_name = "N/A"
            bus_id = "N/A"
            total_mem_mib = 0.0
            used_mem_mib = 0.0
            free_mem_mib = 0.0

            try:
                # Get the device handle
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)

                # --- Device ID & Name ---
                device_id = i
                device_name_bytes = pynvml.nvmlDeviceGetName(handle)
                device_name = (
                    device_name_bytes.decode("utf-8")
                    if isinstance(device_name_bytes, bytes)
                    else device_name_bytes
                )

                # --- Other HW Specs ---
                # PCI Info
                pci_info = pynvml.nvmlDeviceGetPciInfo(handle)
                bus_id_bytes = pci_info.busId
                bus_id = (
                    bus_id_bytes.decode("utf-8")
                    if isinstance(bus_id_bytes, bytes)
                    else bus_id_bytes
                )

                # Memory Info
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                total_mem_mib = mem_info.total / (1024**2)
                used_mem_mib = mem_info.used / (1024**2)
                free_mem_mib = mem_info.free / (1024**2)

                # Temperature
                try:
                    temperature = pynvml.nvmlDeviceGetTemperature(
                        handle, pynvml.NVML_TEMPERATURE_GPU
                    )
                except pynvml.NVMLError:
                    pass  # Keep default -1

                # Fan Speed
                try:
                    fan_speed = pynvml.nvmlDeviceGetFanSpeed(handle)
                except pynvml.NVMLError:
                    pass

                # Power Usage and Limit
                try:
                    power_usage_mw = pynvml.nvmlDeviceGetPowerUsage(handle)
                    power_limit_mw = pynvml.nvmlDeviceGetEnforcedPowerLimit(handle)
                except pynvml.NVMLError:
                    pass

                # Utilization Rates
                try:
                    utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
                    gpu_utilization = utilization.gpu
                    mem_utilization = utilization.memory
                except pynvml.NVMLError:
                    pass

                # Clock Speeds
                try:
                    graphics_clock_mhz = pynvml.nvmlDeviceGetClockInfo(
                        handle, pynvml.NVML_CLOCK_GRAPHICS
                    )
                    mem_clock_mhz = pynvml.nvmlDeviceGetClockInfo(
                        handle, pynvml.NVML_CLOCK_MEM
                    )

                except pynvml.NVMLError:
                    pass

                # *** CORRECTED Pydantic Instantiation ***
                gpu_data = GPUInfo(
                    gpu_id=device_id,  # Use correct field name: gpu_id
                    name=device_name,
                    driver_version=driver_version,  # Pass the driver version
                    pci_bus_id=bus_id,
                    gpu_utilization=gpu_utilization,
                    graphics_clock_mhz=graphics_clock_mhz,
                    mem_utilization=mem_utilization,
                    mem_clock_mhz=mem_clock_mhz,
                    memory_total_mib=total_mem_mib,
                    memory_used_mib=used_mem_mib,
                    memory_free_mib=free_mem_mib,
                    temperature=temperature,
                    fan_speed=fan_speed,
                    power_usage_mw=power_usage_mw,
                    power_limit_mw=power_limit_mw,
                )
                gpu_info_list.append(gpu_data)

            except pynvml.NVMLError:
                pass

    except ImportError:
        return []
    except pynvml.NVMLError:
        return []
    finally:
        if nvml_initialized:
            try:
                pynvml.nvmlShutdown()
            except pynvml.NVMLError as shutdown_error:
                print(f"WARN: Error during nvmlShutdown: {shutdown_error}")

    return gpu_info_list


if __name__ == "__main__":
    # No need for json.dumps, Pydantic models have built-in methods
    gpu_info_results = get_gpu_info()

    print("\nGPU Information:")
    if not gpu_info_results:
        print("No GPU information could be retrieved.")
    else:
        for info in gpu_info_results:
            print(info.model_dump_json(indent=2))
