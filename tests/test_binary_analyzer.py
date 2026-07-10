import os
import struct
import unittest
import tempfile
import logging
from agents.binary_analyzer.agent import BinaryAnalyzerAgent

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class TestBinaryAnalyzer(unittest.TestCase):
    def setUp(self):
        self.agent = BinaryAnalyzerAgent()

    def test_invalid_inputs(self):
        # Missing file_path
        res = self.agent.execute({})
        self.assertEqual(res["status"], "error")
        self.assertIn("Invalid inputs", res["message"])

        # Non-existent file
        res = self.agent.execute({"file_path": "non_existent_file_path_123.bin"})
        self.assertEqual(res["status"], "error")
        self.assertIn("File does not exist", res["message"])

    def test_mock_elf_parsing(self):
        # Create a mock ELF-64 little-endian binary file
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
            try:
                # 1. ELF Identification (16 bytes)
                # magic (4B), class=2 (64-bit) (1B), data=1 (LSB) (1B), version=1 (1B), abi=3 (Linux) (1B)
                ident = b"\x7fELF\x02\x01\x01\x03" + b"\x00" * 8
                
                # 2. ELF Header remainder (ELF64 is 48 bytes remaining)
                # Type=3 (Shared library) (2B), Machine=0x3e (x86_64) (2B), Version=1 (4B)
                # Entry=0x1000 (8B), Phoff=64 (8B), Shoff=0 (8B), Flags=0 (4B)
                # Ehsize=64 (2B), Phentsize=56 (2B), Phnum=2 (2B), Shentsize=0 (2B), Shnum=0 (2B), Shstrndx=0 (2B)
                header_rem = struct.pack(
                    "<HHIQQQIHHHHHH",
                    3, 0x3e, 1, 0x1000, 64, 0, 0, 64, 56, 2, 0, 0, 0
                )
                
                # Write Ident + Header (Total 64 bytes)
                tmp.write(ident + header_rem)
                
                # 3. Write Program Headers (2 headers, each 56 bytes)
                # Phnum=2. 
                # - First Header: Type=1 (PT_LOAD), Flags=5 (RX), Offset=0, Vaddr=0x1000, Paddr=0x1000, Filesz=500, Memsz=500, Align=0x1000
                ph1 = struct.pack("<IIQQQQQQ", 1, 5, 0, 0x1000, 0x1000, 500, 500, 0x1000)
                # - Second Header: Type=2 (PT_DYNAMIC), Flags=6 (RW), Offset=200, Vaddr=0x2000, Paddr=0x2000, Filesz=32, Memsz=32, Align=8
                ph2 = struct.pack("<IIQQQQQQ", 2, 6, 200, 0x2000, 0x2000, 32, 32, 8)
                tmp.write(ph1 + ph2)
                
                # 4. Fill space up to Offset=200 (PT_DYNAMIC start)
                current_len = 64 + 56 * 2
                tmp.write(b"\x00" * (200 - current_len))
                
                # 5. Write PT_DYNAMIC structure at offset 200 (contains 2 entries of 16 bytes each)
                # Entry 1: Tag=5 (DT_STRTAB), Value/Ptr=0x2080 (virtual address of strtab)
                dyn_entry1 = struct.pack("<QQ", 5, 0x2080)
                # Entry 2: Tag=1 (DT_NEEDED), Value=0 (offset in strtab for libname)
                dyn_entry2 = struct.pack("<QQ", 1, 0)
                # Entry 3: Tag=0 (DT_NULL), Value=0
                dyn_entry3 = struct.pack("<QQ", 0, 0)
                tmp.write(dyn_entry1 + dyn_entry2 + dyn_entry3)
                
                # 6. Fill space up to 0x2080 virtual address (mapped to offset 200 + (0x2080 - 0x2000) = 328 file offset)
                current_len = 200 + 16 * 3
                tmp.write(b"\x00" * (328 - current_len))
                
                # Write string table contents: "libc.so.6\0"
                tmp.write(b"libc.so.6\0")
                tmp.flush()
                
                # Execute agent on mock ELF
                res = self.agent.execute({"file_path": tmp_path})
                self.assertEqual(res["status"], "success")
                self.assertEqual(res["format"], "ELF")
                self.assertEqual(res["bitness"], 64)
                self.assertEqual(res["os"], "Linux")
                self.assertEqual(res["architecture"], "x86_64")
                self.assertIn("libc.so.6", res["dependencies"])
                
            finally:
                os.unlink(tmp_path)

    def test_mock_pe_parsing(self):
        # Create a mock PE-64 little-endian binary file
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
            try:
                # 1. DOS Header (64 bytes)
                dos_hdr = bytearray(64)
                dos_hdr[:2] = b"MZ"
                # PE offset is at 0x3c (set to 64)
                dos_hdr[0x3c:0x40] = struct.pack("<I", 64)
                tmp.write(dos_hdr)
                
                # 2. PE Signature
                tmp.write(b"PE\0\0")
                
                # 3. COFF Header (20 bytes)
                # Machine=0x8664 (AMD64) (2B), NumSections=1 (2B), Time=0 (4B), PointerToSymbolTable=0 (4B),
                # NumSymbols=0 (4B), SizeOfOptionalHeader=240 (2B), Characteristics=0x22 (2B)
                coff_hdr = struct.pack("<HHIIIHH", 0x8664, 1, 0, 0, 0, 240, 0x22)
                tmp.write(coff_hdr)
                
                # 4. Optional Header (240 bytes)
                # Magic=0x20b (PE32+) (2B)
                opt_hdr = bytearray(240)
                opt_hdr[:2] = struct.pack("<H", 0x20b)
                
                # Data directories start at index 112 (PE32+)
                # We write dir_count = 16 (4 bytes) at offset 108
                opt_hdr[108:112] = struct.pack("<I", 16)
                
                # Import directory (index 1) has VirtualAddress and Size
                # Address=0x2000, Size=40. Located at offset 112 + 8 = 120
                opt_hdr[120:128] = struct.pack("<II", 0x2000, 40)
                tmp.write(opt_hdr)
                
                # 5. Section Table (1 section, each 40 bytes)
                # Name=".rdata\0\0", VSize=1000, VAddr=0x2000, RawSize=512, RawPtr=512
                section = struct.pack(
                    "<8sIIIIIIHHI",
                    b".rdata", 1000, 0x2000, 512, 512, 0, 0, 0, 0, 0
                )
                tmp.write(section)
                
                # Fill up to RawPtr=512
                current_len = 64 + 4 + 20 + 240 + 40
                tmp.write(b"\x00" * (512 - current_len))
                
                # At file offset 512 (which maps to RVA 0x2000), we write Import Table
                # Directory descriptor (20 bytes)
                # lookup_rva=0x2030, time=0, forward=0, name_rva=0x2050, address_rva=0x2030
                import_desc = struct.pack("<IIIII", 0x2030, 0, 0, 0x2050, 0x2030)
                # Null descriptor to terminate
                null_desc = b"\x00" * 20
                tmp.write(import_desc + null_desc)
                
                # Seek to 0x2050 (file offset 512 + (0x2050 - 0x2000) = 592) and write DLL name "KERNEL32.dll\0"
                current_len = 512 + 40
                tmp.write(b"\x00" * (592 - current_len))
                tmp.write(b"KERNEL32.dll\0")
                tmp.flush()
                
                # Execute agent on mock PE
                res = self.agent.execute({"file_path": tmp_path})
                self.assertEqual(res["status"], "success")
                self.assertEqual(res["format"], "PE")
                self.assertEqual(res["bitness"], 64)
                self.assertEqual(res["os"], "Windows")
                self.assertEqual(res["architecture"], "x86_64")
                self.assertIn("KERNEL32.dll", res["dependencies"])
                
            finally:
                os.unlink(tmp_path)

    def test_system_binary_parsing(self):
        # Find a common system binary
        candidates = ["/bin/ls", "/bin/sh", "/usr/bin/python3"]
        target = None
        for cand in candidates:
            if os.path.exists(cand) and os.path.isfile(cand):
                target = cand
                break
                
        if target:
            res = self.agent.execute({"file_path": target})
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["format"], "ELF")
            self.assertEqual(res["os"], "Linux")
            self.assertGreater(len(res["dependencies"]), 0)
            logger.info(f"System binary {target} parsed successfully: {res}")
        else:
            self.skipTest("No system binaries found to test against")


if __name__ == "__main__":
    unittest.main()
