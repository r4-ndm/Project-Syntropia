import os
import struct
import subprocess
import functools
import logging
from typing import Dict, Any, List, Optional, Tuple

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BinaryAnalyzerAgent")


@functools.lru_cache(maxsize=1024)
def _analyze_file_cached(filepath: str, file_size: int, mtime: float) -> Dict[str, Any]:
    """
    Cached worker function to analyze binary files.
    Keyed by filepath, file size, and modification time to ensure cache freshness.
    """
    # 1. Try pure-Python parsers
    try:
        with open(filepath, "rb") as f:
            magic_bytes = f.read(4)
            if len(magic_bytes) < 4:
                return {
                    "format": "Unknown",
                    "bitness": 64,
                    "endianness": "little",
                    "os": "Unknown",
                    "architecture": "Unknown",
                    "dependencies": [],
                    "confidence": 0.0,
                    "error": "File too short"
                }

            if magic_bytes == b"\x7fELF":
                return _parse_elf(filepath)
            elif magic_bytes[:2] == b"MZ":
                return _parse_pe(filepath)
            elif magic_bytes in (b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"):
                return _parse_macho(filepath)
    except Exception as e:
        logger.warning(f"Pure-Python parsing failed for {filepath}: {e}")

    # 2. Fall back to system command analysis
    logger.info(f"Falling back to system commands for {filepath}")
    return _run_command_fallback(filepath)


def _parse_elf(filepath: str) -> Dict[str, Any]:
    """Pure-Python ELF header parser targeting Linux/Unix binaries."""
    with open(filepath, "rb") as f:
        ident = f.read(16)
        if len(ident) < 16 or ident[:4] != b"\x7fELF":
            raise ValueError("Not a valid ELF file")
            
        elf_class = ident[4]  # 1 = 32-bit, 2 = 64-bit
        elf_data = ident[5]   # 1 = LSB/little-endian, 2 = MSB/big-endian
        os_abi = ident[7]
        
        is_64bit = elf_class == 2
        is_little_endian = elf_data == 1
        endian_char = "<" if is_little_endian else ">"
        
        abi_map = {
            0x00: "Linux",  # System V is the default Linux ABI
            0x01: "HP-UX",
            0x02: "NetBSD",
            0x03: "Linux",
            0x06: "Solaris",
            0x07: "AIX",
            0x08: "IRIX",
            0x09: "FreeBSD",
            0x0C: "OpenBSD",
        }
        os_name = abi_map.get(os_abi, "Linux")
        
        # Read remainder of the header
        rem_size = 48 if is_64bit else 36
        rem_bytes = f.read(rem_size)
        if len(rem_bytes) < rem_size:
            raise ValueError("Corrupt ELF header")
            
        if is_64bit:
            e_type, machine, _, _, phoff, shoff, _, _, phentsize, phnum, _, _, _ = struct.unpack(
                endian_char + "HHIQQQIHHHHHH", rem_bytes[:48]
            )
        else:
            e_type, machine, _, _, phoff, shoff, _, _, phentsize, phnum, _, _, _ = struct.unpack(
                endian_char + "HHIIIIIHHHHHH", rem_bytes[:36]
            )
            
        machine_map = {
            0x03: "x86",
            0x28: "arm",
            0x3e: "x86_64",
            0xb7: "aarch64",
            0x08: "mips",
            0xf3: "riscv",
        }
        arch = machine_map.get(machine, "Unknown")
        
        # Program Headers to translate addresses
        f.seek(phoff)
        ph_entries = []
        for _ in range(phnum):
            ph_bytes = f.read(phentsize)
            if len(ph_bytes) < phentsize:
                break
            if is_64bit:
                p_type, p_flags, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_align = struct.unpack(
                    endian_char + "IIQQQQQQ", ph_bytes[:56]
                )
            else:
                p_type, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_flags, p_align = struct.unpack(
                    endian_char + "IIIIIIII", ph_bytes[:32]
                )
            ph_entries.append((p_type, p_offset, p_vaddr, p_filesz))
            
        def vaddr_to_offset(vaddr: int) -> Optional[int]:
            for p_type, p_offset, p_vaddr, p_filesz in ph_entries:
                if p_type == 1:  # PT_LOAD
                    if p_vaddr <= vaddr < p_vaddr + p_filesz:
                        return p_offset + (vaddr - p_vaddr)
            return None

        # Find PT_DYNAMIC segment (type 2)
        dynamic_offset = None
        dynamic_filesz = None
        dynamic_vaddr = None
        for p_type, p_offset, p_vaddr, p_filesz in ph_entries:
            if p_type == 2:  # PT_DYNAMIC
                dynamic_offset = p_offset
                dynamic_vaddr = p_vaddr
                dynamic_filesz = p_filesz
                break
                
        dependencies = []
        if dynamic_offset is not None and dynamic_filesz is not None:
            entry_size = 16 if is_64bit else 8
            tag_fmt = "Q" if is_64bit else "I"
            
            f.seek(dynamic_offset)
            entries = []
            for _ in range(dynamic_filesz // entry_size):
                entry_bytes = f.read(entry_size)
                if len(entry_bytes) < entry_size:
                    break
                tag, val = struct.unpack(endian_char + tag_fmt + tag_fmt, entry_bytes)
                if tag == 0:  # DT_NULL
                    break
                entries.append((tag, val))
                
            strtab_vaddr = None
            needed_offsets = []
            for tag, val in entries:
                if tag == 5:  # DT_STRTAB
                    strtab_vaddr = val
                elif tag == 1:  # DT_NEEDED
                    needed_offsets.append(val)
                    
            if strtab_vaddr is not None:
                strtab_offset = vaddr_to_offset(strtab_vaddr)
                if strtab_offset is None and dynamic_vaddr is not None:
                    # Direct relative offset fallback
                    strtab_offset = dynamic_offset + (strtab_vaddr - dynamic_vaddr)
                
                if strtab_offset is not None:
                    for offset in needed_offsets:
                        f.seek(strtab_offset + offset)
                        lib_name_bytes = bytearray()
                        while True:
                            b = f.read(1)
                            if not b or b == b"\0":
                                break
                            lib_name_bytes.extend(b)
                        if lib_name_bytes:
                            dependencies.append(lib_name_bytes.decode("utf-8", errors="ignore"))
                            
        return {
            "format": "ELF",
            "bitness": 64 if is_64bit else 32,
            "endianness": "little" if is_little_endian else "big",
            "os": os_name,
            "architecture": arch,
            "dependencies": list(set(dependencies)),
            "confidence": 1.0,
        }


def _parse_pe(filepath: str) -> Dict[str, Any]:
    """Pure-Python PE (Portable Executable) parser targeting Windows binaries."""
    with open(filepath, "rb") as f:
        dos_hdr = f.read(64)
        if len(dos_hdr) < 64 or dos_hdr[:2] != b"MZ":
            raise ValueError("Not a valid PE file (missing MZ signature)")
        
        pe_offset = struct.unpack("<I", dos_hdr[0x3c:0x40])[0]
        
        f.seek(pe_offset)
        pe_sig = f.read(4)
        if pe_sig != b"PE\0\0":
            raise ValueError("Not a valid PE file (missing PE signature)")
            
        coff_hdr = f.read(20)
        if len(coff_hdr) < 20:
            raise ValueError("Corrupt PE COFF Header")
            
        machine, num_sections, _, _, _, opt_hdr_size, _ = struct.unpack(
            "<HHIIIHH", coff_hdr
        )
        
        machine_map = {
            0x14c: ("x86", "Windows"),
            0x8664: ("x86_64", "Windows"),
            0xaa64: ("arm64", "Windows"),
            0x1c0: ("arm", "Windows"),
            0x200: ("ia64", "Windows"),
        }
        arch, os_name = machine_map.get(machine, ("Unknown", "Windows"))
        
        opt_offset = pe_offset + 24
        f.seek(opt_offset)
        magic_bytes = f.read(2)
        if len(magic_bytes) < 2:
            raise ValueError("Corrupt Optional Header magic")
        opt_magic = struct.unpack("<H", magic_bytes)[0]
        
        if opt_magic == 0x10b:  # PE32
            is_64bit = False
            dir_count_offset = 92
        elif opt_magic == 0x20b:  # PE32+ (64-bit)
            is_64bit = True
            dir_count_offset = 108
        else:
            raise ValueError(f"Unknown PE optional header magic: {hex(opt_magic)}")
            
        f.seek(opt_offset + dir_count_offset)
        dir_count_bytes = f.read(4)
        if len(dir_count_bytes) < 4:
            raise ValueError("Corrupt directory count")
        dir_count = struct.unpack("<I", dir_count_bytes)[0]
        
        if dir_count < 2:
            return {
                "format": "PE",
                "bitness": 64 if is_64bit else 32,
                "endianness": "little",
                "os": os_name,
                "architecture": arch,
                "dependencies": [],
                "confidence": 0.9,
            }
            
        # Import directory is index 1
        f.seek(opt_offset + dir_count_offset + 4 + 8)
        import_dir_bytes = f.read(8)
        if len(import_dir_bytes) < 8:
            raise ValueError("Corrupt Import Directory entry")
        import_rva, import_size = struct.unpack("<II", import_dir_bytes)
        
        # Read Sections
        sec_offset = opt_offset + opt_hdr_size
        f.seek(sec_offset)
        sections = []
        for _ in range(num_sections):
            sec_bytes = f.read(40)
            if len(sec_bytes) < 40:
                break
            name = sec_bytes[:8].rstrip(b"\0").decode("utf-8", errors="ignore")
            v_size, v_addr, raw_size, raw_ptr = struct.unpack("<IIII", sec_bytes[8:24])
            sections.append((name, v_addr, v_size, raw_ptr, raw_size))
            
        def rva_to_offset(rva: int) -> Optional[int]:
            for name, v_addr, v_size, raw_ptr, raw_size in sections:
                if v_addr <= rva < v_addr + max(v_size, raw_size):
                    return raw_ptr + (rva - v_addr)
            return None

        dependencies = []
        if import_rva > 0 and import_size > 0:
            import_file_offset = rva_to_offset(import_rva)
            if import_file_offset is not None:
                f.seek(import_file_offset)
                while True:
                    desc_bytes = f.read(20)
                    if len(desc_bytes) < 20 or desc_bytes == b"\0" * 20:
                        break
                    
                    lookup_rva, _, _, name_rva, _ = struct.unpack("<IIIII", desc_bytes)
                    if lookup_rva == 0 and name_rva == 0:
                        break
                    
                    name_offset = rva_to_offset(name_rva)
                    if name_offset is not None:
                        current_pos = f.tell()
                        f.seek(name_offset)
                        dll_name_bytes = bytearray()
                        while True:
                            b = f.read(1)
                            if not b or b == b"\0":
                                break
                            dll_name_bytes.extend(b)
                        if dll_name_bytes:
                            dependencies.append(dll_name_bytes.decode("utf-8", errors="ignore"))
                        f.seek(current_pos)
                        
        return {
            "format": "PE",
            "bitness": 64 if is_64bit else 32,
            "endianness": "little",
            "os": os_name,
            "architecture": arch,
            "dependencies": list(set(dependencies)),
            "confidence": 1.0,
        }


def _parse_macho(filepath: str) -> Dict[str, Any]:
    """Pure-Python Mach-O parser targeting macOS binaries."""
    with open(filepath, "rb") as f:
        magic_bytes = f.read(4)
        if len(magic_bytes) < 4:
            raise ValueError("File too short for Mach-O")
        magic = struct.unpack(">I", magic_bytes)[0]
        
        is_fat = magic in (0xcafebabe, 0xbebafeca)
        is_cigam = magic in (0xcefaedfe, 0xcffaedfe, 0xbebafeca)
        is_64bit = magic in (0xfeedfacf, 0xcffaedfe)
        endian_char = ">" if is_cigam else "<"
        
        if is_fat:
            nfat_bytes = f.read(4)
            if len(nfat_bytes) < 4:
                raise ValueError("Corrupt Mach-O FAT header")
            nfat = struct.unpack(endian_char + "I", nfat_bytes)[0]
            
            # Read first fat_arch
            arch_bytes = f.read(20)
            if len(arch_bytes) < 20:
                raise ValueError("Corrupt fat_arch entry")
            _, _, arch_offset, _, _ = struct.unpack(endian_char + "IIIII", arch_bytes)
            
            f.seek(arch_offset)
            magic_bytes = f.read(4)
            magic = struct.unpack(endian_char + "I", magic_bytes)[0]
            is_64bit = magic in (0xfeedfacf, 0xcffaedfe)
            
        hdr_size = 28 if is_64bit else 24
        hdr_bytes = f.read(hdr_size)
        if len(hdr_bytes) < hdr_size:
            raise ValueError("Corrupt Mach-O header")
            
        cputype, _, _, ncmds, _, _ = struct.unpack(
            endian_char + "IIIIII", hdr_bytes[:24]
        )
        
        cpu_map = {
            7: "x86",
            0x01000007: "x86_64",
            12: "arm",
            0x0100000c: "arm64",
            18: "ppc",
            0x01000012: "ppc64",
        }
        arch = cpu_map.get(cputype, "Unknown")
        
        dependencies = []
        for _ in range(ncmds):
            cmd_hdr = f.read(8)
            if len(cmd_hdr) < 8:
                break
            cmd, cmdsize = struct.unpack(endian_char + "II", cmd_hdr)
            
            if cmd in (0x0c, 0x80000018, 0x8000001f):
                cmd_data = f.read(cmdsize - 8)
                if len(cmd_data) >= 16:
                    name_offset = struct.unpack(endian_char + "I", cmd_data[:4])[0]
                    name_ptr = name_offset - 8
                    if 0 <= name_ptr < len(cmd_data):
                        lib_name_bytes = cmd_data[name_ptr:].split(b"\0")[0]
                        if lib_name_bytes:
                            lib_name = lib_name_bytes.decode("utf-8", errors="ignore")
                            dependencies.append(os.path.basename(lib_name))
            else:
                f.seek(cmdsize - 8, os.SEEK_CUR)
                
        return {
            "format": "Mach-O",
            "bitness": 64 if is_64bit else 32,
            "endianness": "little" if not is_cigam else "big",
            "os": "macOS",
            "architecture": arch,
            "dependencies": list(set(dependencies)),
            "confidence": 1.0,
        }


def _run_command_fallback(filepath: str) -> Dict[str, Any]:
    """Runs system commands like file, ldd, readelf to analyze binaries."""
    res = {
        "format": "Unknown",
        "bitness": 64,
        "endianness": "little",
        "os": "Unknown",
        "architecture": "Unknown",
        "dependencies": [],
        "confidence": 0.4,
    }
    
    # 1. Use 'file'
    try:
        proc = subprocess.run(["file", filepath], capture_output=True, text=True, timeout=5)
        if proc.returncode == 0:
            output = proc.stdout.lower()
            if "elf" in output:
                res["format"] = "ELF"
                res["os"] = "Linux"
                res["confidence"] = 0.6
                if "64-bit" in output:
                    res["bitness"] = 64
                elif "32-bit" in output:
                    res["bitness"] = 32
                if "x86-64" in output or "amd64" in output:
                    res["architecture"] = "x86_64"
                elif "intel 80386" in output:
                    res["architecture"] = "x86"
                elif "aarch64" in output or "arm64" in output:
                    res["architecture"] = "arm64"
                elif "arm" in output:
                    res["architecture"] = "arm"
                if "msb" in output:
                    res["endianness"] = "big"
            elif "pe32" in output:
                res["format"] = "PE"
                res["os"] = "Windows"
                res["confidence"] = 0.6
                if "pe32+" in output:
                    res["bitness"] = 64
                    res["architecture"] = "x86_64"
                else:
                    res["bitness"] = 32
                    res["architecture"] = "x86"
            elif "mach-o" in output:
                res["format"] = "Mach-O"
                res["os"] = "macOS"
                res["confidence"] = 0.6
                if "64-bit" in output:
                    res["bitness"] = 64
                if "x86_64" in output:
                    res["architecture"] = "x86_64"
                elif "arm64" in output:
                    res["architecture"] = "arm64"
    except Exception as e:
        logger.warning(f"file command fallback failed: {e}")

    # 2. Use 'ldd' or 'readelf' for ELF
    if res["format"] == "ELF":
        try:
            proc = subprocess.run(["ldd", filepath], capture_output=True, text=True, timeout=5)
            if proc.returncode == 0:
                deps = []
                for line in proc.stdout.splitlines():
                    line = line.strip()
                    if "=>" in line:
                        lib = line.split("=>")[0].strip()
                        if lib:
                            deps.append(lib)
                    elif line and not line.startswith("/"):
                        lib = line.split()[0]
                        deps.append(lib)
                res["dependencies"] = list(set(deps))
                res["confidence"] = 0.8
        except Exception:
            try:
                proc = subprocess.run(["readelf", "-d", filepath], capture_output=True, text=True, timeout=5)
                if proc.returncode == 0:
                    deps = []
                    for line in proc.stdout.splitlines():
                        if "NEEDED" in line and "[" in line and "]" in line:
                            lib = line.split("[")[1].split("]")[0]
                            deps.append(lib)
                    res["dependencies"] = list(set(deps))
                    res["confidence"] = 0.8
            except Exception as e:
                logger.warning(f"ldd/readelf fallback failed: {e}")

    return res


class BinaryAnalyzerAgent:
    """
    Binary Analyzer Agent.
    Strictly follows Syntropia execution framework.
    """
    def __init__(self):
        self.role = "binary_analyzer"
        self.timeout = 5  # ticks

    def execute(self, inputs: Any) -> Dict[str, Any]:
        """
        Executes analysis on target executable file.
        Inputs: A path string or a dictionary containing 'file_path' or 'data'.
        """
        filepath = None
        if isinstance(inputs, str):
            filepath = inputs
        elif isinstance(inputs, dict):
            filepath = inputs.get("file_path")
            
        if not filepath:
            return {
                "status": "error",
                "message": "Invalid inputs. Expected dictionary with 'file_path' or path string."
            }
            
        if not os.path.exists(filepath):
            return {
                "status": "error",
                "message": f"File does not exist: {filepath}"
            }
            
        try:
            stat = os.stat(filepath)
            # Use cached worker utilizing file_path, file_size, and mtime
            analysis = _analyze_file_cached(filepath, stat.st_size, stat.st_mtime)
            
            # Optional: Add raw debug bytes if debug mode is active
            if isinstance(inputs, dict) and inputs.get("debug"):
                with open(filepath, "rb") as f:
                    hdr_bytes = f.read(128)
                    analysis["debug_hexdump"] = hdr_bytes.hex()
                    
            return {
                "status": "success",
                **analysis
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Execution failed: {str(e)}"
            }
