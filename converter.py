import os
import struct
import sys
import dds
import customtkinter
import tkinter
from tkinter import filedialog
from tkinter import scrolledtext
from tkinter.filedialog import askdirectory
from customtkinter import *
from threading import Thread

try:
    import pyximport
    pyximport.install()
    import swizzle_cy as swizzle
except ImportError:
    import swizzle

DIV_ROUND_UP = swizzle.DIV_ROUND_UP


formats = {
    0x0b01: 'R8_G8_B8_A8_UNORM',
    0x0b06: 'R8_G8_B8_A8_SRGB',
    0x0701: 'R5_G6_B5_UNORM',
    0x0201: 'R8_UNORM',
    0x0901: 'R8_G8_UNORM',
    0x1a01: 'BC1_UNORM',
    0x1a06: 'BC1_SRGB',
    0x1b01: 'BC2_UNORM',
    0x1b06: 'BC2_SRGB',
    0x1c01: 'BC3_UNORM',
    0x1c06: 'BC3_SRGB',
    0x1d01: 'BC4_UNORM',
    0x1d02: 'BC4_SNORM',
    0x1e01: 'BC5_UNORM',
    0x1e02: 'BC5_SNORM',
    0x1f01: 'BC6H_UF16',
    0x1f02: 'BC6H_SF16',
    0x2001: 'BC7_UNORM',
    0x2006: 'BC7_SRGB',
    0x2d01: 'ASTC4x4',
    0x2d06: 'ASTC4x4 SRGB',
    0x2e01: 'ASTC5x4',
    0x2e06: 'ASTC5x4 SRGB',
    0x2f01: 'ASTC5x5',
    0x2f06: 'ASTC5x5 SRGB',
    0x3001: 'ASTC6x5',
    0x3006: 'ASTC6x5 SRGB',
    0x3101: 'ASTC6x6',
    0x3106: 'ASTC6x6 SRGB',
    0x3201: 'ASTC8x5',
    0x3206: 'ASTC8x5 SRGB',
    0x3301: 'ASTC8x6',
    0x3306: 'ASTC8x6 SRGB',
    0x3401: 'ASTC8x8',
    0x3406: 'ASTC8x8 SRGB',
    0x3501: 'ASTC10x5',
    0x3506: 'ASTC10x5 SRGB',
    0x3601: 'ASTC10x6',
    0x3606: 'ASTC10x6 SRGB',
    0x3701: 'ASTC10x8',
    0x3706: 'ASTC10x8 SRGB',
    0x3801: 'ASTC10x10',
    0x3806: 'ASTC10x10 SRGB',
    0x3901: 'ASTC12x10',
    0x3906: 'ASTC12x10 SRGB',
    0x3a01: 'ASTC12x12',
    0x3a06: 'ASTC12x12 SRGB'
}

BCn_formats = [
    0x1a, 0x1b, 0x1c, 0x1d,
    0x1e, 0x1f, 0x20,
]

ASTC_formats = [
    0x2d, 0x2e, 0x2f, 0x30,
    0x31, 0x32, 0x33, 0x34,
    0x35, 0x36, 0x37, 0x38,
    0x39, 0x3a,
]

blk_dims = {  # format -> (blkWidth, blkHeight)
    0x1a: (4, 4), 0x1b: (4, 4), 0x1c: (4, 4),
    0x1d: (4, 4), 0x1e: (4, 4), 0x1f: (4, 4),
    0x20: (4, 4), 0x2d: (4, 4), 0x2e: (5, 4),
    0x2f: (5, 5), 0x30: (6, 5),
    0x31: (6, 6), 0x32: (8, 5),
    0x33: (8, 6), 0x34: (8, 8),
    0x35: (10, 5), 0x36: (10, 6),
    0x37: (10, 8), 0x38: (10, 10),
    0x39: (12, 10), 0x3a: (12, 12),
}

bpps = {  # format -> bytes_per_pixel
    0x0b: 0x04, 0x07: 0x02, 0x02: 0x01, 0x09: 0x02, 0x1a: 0x08,
    0x1b: 0x10, 0x1c: 0x10, 0x1d: 0x08, 0x1e: 0x10, 0x1f: 0x10,
    0x20: 0x10, 0x2d: 0x10, 0x2e: 0x10, 0x2f: 0x10, 0x30: 0x10,
    0x31: 0x10, 0x32: 0x10, 0x33: 0x10, 0x34: 0x10, 0x35: 0x10,
    0x36: 0x10, 0x37: 0x10, 0x38: 0x10, 0x39: 0x10, 0x3a: 0x10,
}


def bytes_to_string(data, end=0):
    if not end:
        end = data.find(b'\0')
        if end == -1:
            return data.decode('utf-8')

    return data[:end].decode('utf-8')


class BNTXHeader(struct.Struct):
    def __init__(self, bom):
        super().__init__(bom + '8si2Hi2xh2i')

    def data(self, data, pos):
        (self.magic,
         self.version,
         self.bom,
         self.revision,
         self.fileNameAddr,
         self.strAddr,
         self.relocAddr,
         self.fileSize) = self.unpack_from(data, pos)


class NXHeader(struct.Struct):
    def __init__(self, bom):
        super().__init__(bom + '4sI3qI')

    def data(self, data, pos):
        (self.magic,
         self.count,
         self.infoPtrAddr,
         self.dataBlkAddr,
         self.dictAddr,
         self.strDictSize) = self.unpack_from(data, pos)


class BRTIInfo(struct.Struct):
    def __init__(self, bom):
        super().__init__(bom + '4siq2b3H3I5i6I4i3q')

    def data(self, data, pos):
        (self.magic,
         self.size_,
         self.size_2,
         self.tileMode,
         self.dim,
         self.flags,
         self.swizzle,
         self.numMips,
         self.unk18,
         self.format_,
         self.unk20,
         self.width,
         self.height,
         self.unk2C,
         self.numFaces,
         self.sizeRange,
         self.unk38,
         self.unk3C,
         self.unk40,
         self.unk44,
         self.unk48,
         self.unk4C,
         self.imageSize,
         self.alignment,
         self.compSel,
         self.type_,
         self.nameAddr,
         self.parentAddr,
         self.ptrsAddr) = self.unpack_from(data, pos)


class TexInfo:
    pass

tileModes = {0: "TILING_MODE_PITCH", 1: "TILING_MODE_TILED"}

def get_tile_mode(tile_mode):
    return tileModes.get(tile_mode, f"Unknown ({tile_mode})")

def readBNTX(f):
    pos = 0

    if f[0xc:0xe] == b'\xFF\xFE':
        bom = '<'

    elif f[0xc:0xe] == b'\xFE\xFF':
        bom = '>'

    else:
        raise ValueError("Invalid BOM!")

    header = BNTXHeader(bom)
    header.data(f, pos)
    pos += header.size

    if bytes_to_string(header.magic, 4) != "BNTX":
        raise ValueError("Invalid file header!")

    nx = NXHeader(bom)
    nx.data(f, pos)
    pos += nx.size


    textures = []

    for i in range(nx.count):
        pos = nx.infoPtrAddr + i * 8

        pos = struct.unpack(bom + 'q', f[pos:pos+8])[0]

        info = BRTIInfo(bom)
        info.data(f, pos)

        nameLen = struct.unpack(bom + 'H', f[info.nameAddr:info.nameAddr + 2])[0]
        name = bytes_to_string(f[info.nameAddr + 2:info.nameAddr + 2 + nameLen], nameLen)

        compSel = []
        compSels = {0: "0", 1: "1", 2: "Red", 3: "Green", 4: "Blue", 5: "Alpha"}
        for i in range(4):
            value = (info.compSel >> (8 * (3 - i))) & 0xff
            if value == 0:
                value = len(compSel) + 2

            compSel.append(value)

        types = {0: "1D", 1: "2D", 2: "3D", 3: "Cubemap", 8: "CubemapFar"}
        if info.type_ not in types:
            types[info.type_] = "Unknown"

        tileModes = {0: "TILING_MODE_PITCH", 1: "TILING_MODE_TILED"}

        dataAddr = struct.unpack(bom + 'q', f[info.ptrsAddr:info.ptrsAddr + 8])[0]
        mipOffsets = {0: 0}

        for i in range(1, info.numMips):
            mipOffset = struct.unpack(bom + 'q', f[info.ptrsAddr + (i * 8):info.ptrsAddr + (i * 8) + 8])[0]
            mipOffsets[i] = mipOffset - dataAddr

        tex = TexInfo()
        tex.name = name
        tex.tileMode = info.tileMode
        tex.numMips = info.numMips
        tex.mipOffsets = mipOffsets
        tex.width = info.width
        tex.height = info.height
        tex.format = info.format_
        tex.numFaces = info.numFaces
        tex.sizeRange = info.sizeRange
        tex.compSel = compSel
        tex.alignment = info.alignment
        tex.type = info.type_
        tex.data = f[dataAddr:dataAddr+info.imageSize]

        textures.append(tex)

    return textures


def saveTextures(textures, folder_path):
    input_folder = folder_path
    for tex in textures:
        if tex.format in formats and tex.numFaces < 2:
            if (tex.format >> 8) == 0xb:
                format_ = 28

            elif tex.format == 0x701:
                format_ = 85

            elif tex.format == 0x201:
                format_ = 61

            elif tex.format == 0x901:
                format_ = 49

            elif (tex.format >> 8) == 0x1a:
                format_ = "BC1"

            elif (tex.format >> 8) == 0x1b:
                format_ = "BC2"

            elif (tex.format >> 8) == 0x1c:
                format_ = "BC3"

            elif tex.format == 0x1d01:
                format_ = "BC4U"

            elif tex.format == 0x1d02:
                format_ = "BC4S"

            elif tex.format == 0x1e01:
                format_ = "BC5U"

            elif tex.format == 0x1e02:
                format_ = "BC5S"

            elif tex.format == 0x1f01:
                format_ = "BC6H_UF16"

            elif tex.format == 0x1f02:
                format_ = "BC6H_SF16"

            elif (tex.format >> 8) == 0x20:
                format_ = "BC7"

            if (tex.format >> 8) in blk_dims:
                blkWidth, blkHeight = blk_dims[tex.format >> 8]

            else:
                blkWidth, blkHeight = 1, 1

            bpp = bpps[tex.format >> 8]

            size = DIV_ROUND_UP(tex.width, blkWidth) * DIV_ROUND_UP(tex.height, blkHeight) * bpp

            result = swizzle.deswizzle(tex.width, tex.height, blkWidth, blkHeight, bpp, tex.tileMode, tex.alignment, tex.sizeRange, tex.data)
            result = result[:size]

            if (tex.format >> 8) in ASTC_formats:
                outBuffer = b''.join([
                    b'\x13\xAB\xA1\x5C', blkWidth.to_bytes(1, "little"),
                    blkHeight.to_bytes(1, "little"), b'\1',
                    tex.width.to_bytes(3, "little"),
                    tex.height.to_bytes(3, "little"), b'\1\0\0',
                    result,
                ])

                with open(tex.name + ".astc", "wb+") as output:
                    output.write(outBuffer)

            else:
                hdr = dds.generateHeader(1, tex.width, tex.height, format_, list(reversed(tex.compSel)), size, (tex.format >> 8) in BCn_formats)

                with open(tex.name + ".dds", "wb+") as output:
                    output.write(b''.join([hdr, result]))
            
            output_folder = os.path.join(input_folder, "converted_textures")
            os.makedirs(output_folder, exist_ok=True)

            if (tex.format >> 8) in ASTC_formats:
                output_path = os.path.join(output_folder, tex.name + ".astc")
                with open(output_path, "wb+") as output:
                    output.write(outBuffer)

            else:
                output_path = os.path.join(output_folder, tex.name + ".dds")
                with open(output_path, "wb+") as output:
                    output.write(b''.join([hdr, result]))

            print(f"Processing {tex.name}")

        else:
            print("")
            print("Can't convert: " + tex.name)

            if tex.format not in formats:
                print("Format is not supported.")

            else:
                print("Unsupported number of faces.")

class PrintRedirector:
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.buffer = ""
        self.text_widget.configure(state='disabled')  # Disable user input
        self.text_widget.tag_configure("custom_tag", background='lightgray', foreground='black')

    def write(self, text):
        self.buffer += text
        self.text_widget.configure(state='normal')  # Enable writing
        self.text_widget.insert("end", text, "custom_tag")  # Apply custom_tag to the inserted text
        self.text_widget.see("end")
        self.text_widget.configure(state='disabled')  # Disable user input again

    def flush(self):
        self.text_widget.configure(state='normal')  # Enable writing
        try:
            self.text_widget.insert("end", self.buffer, "custom_tag")  # Apply custom_tag to the buffered text
        except Exception as e:
            self.text_widget.insert("end", f"Error: {e}\n", "custom_tag")  # Display the exception message with custom_tag
        finally:
            self.text_widget.see("end")
            self.text_widget.configure(state='disabled')  # Disable user input again
            self.buffer = ""

def main(folder_path):

    if not os.path.exists(folder_path):
        print("Error: The specified folder does not exist.")
        sys.exit(1)

    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith(".bntx"):
                input_file = os.path.join(root, file)
                with open(input_file, "rb") as inf:
                    inb = inf.read()

                textures = readBNTX(inb)
                saveTextures(textures, folder_path)

    print("Conversion completed.")

def select_bntx_folder():
    folder_path = askdirectory()
    main(folder_path)

def do_stuff():
    sys.stdout = PrintRedirector(scrolled_text)
    t = Thread(target=select_bntx_folder)
    t.start()

root = customtkinter.CTk()
root.title(f"Convert Robbie Test")
root.geometry("500x520")

customtkinter.set_appearance_mode("system")
customtkinter.set_default_color_theme("blue")  

scrolled_text = scrolledtext.ScrolledText(master=root, width=50, height=18, font=("Helvetica", 10))
scrolled_text.pack(pady=50)

bntx_folder_button = customtkinter.CTkButton(master=root, text="Convert BNTX Folder to ASTC", fg_color="blue", hover_color="darkblue", command=do_stuff)
bntx_folder_button.pack(pady=25)


root.mainloop()
# astcenc-sse4.1.exe -dh source.astc destination.png