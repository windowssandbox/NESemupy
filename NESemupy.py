import os, sys, time

try:
    import pygame
    import numpy as np
except:
    print("you need pygame, numpy, and taichi installed in order to run this")
    input("press enter to exit")
    sys.exit(0)

pygame.init()
win_s = 2
screen = pygame.display.set_mode((256*win_s, 240*win_s))
surf = pygame.Surface((256, 240))

path2romfile = ""
debug_mode = 0
debugrunning = True
pgc = 1

# NES vars:
# | CPU |
PC = 0x0000
A=0; X=0; Y=0; S=0xFD; P=0
C=0; Z=0; I=1; D=0; V=0; N=0
opcode = 0x00

NES_CPU_SPD = 1789773
FPS = 60
TIME_PER_FRAME = 1.0 / FPS
CYCLES_PER_FRAME = int(NES_CPU_SPD / FPS)
cpu_cycles = 0
frame_start_time = 0
instruction_count = 0

RAM = [0x00] * 0x0800
MEM = [0x00] * 0x10000

# | PPU |
VRAM = bytearray(0x4000)
OAM = bytearray(256)
ppu_addr_latch = 0
ppu_addr_point = 0x0000
ppu_stat = 0x00
ppu_ctrl = 0x00
ppu_mask = 0x00
ppu_data_buff = 0x00
ppu_cycles = 0
PPU_CYCLES_PER_FRAME = CYCLES_PER_FRAME*3
VBLANK_START_PPU = 241*341
NES_PAL = [
    "#7C7C7C", "#0000FC", "#0000BC", "#4428BC", "#940084", "#A80020", "#A81000", "#881400",
    "#503000", "#007800", "#006800", "#005800", "#004058", "#000000", "#000000", "#000000",
    "#BCBCBC", "#0078F8", "#0058F8", "#6844FC", "#D800B8", "#E40058", "#F83800", "#E45C10",
    "#AC7C00", "#00B800", "#00A800", "#00A844", "#008888", "#000000", "#000000", "#000000",
    "#F8F8F8", "#3CBCFC", "#6888FC", "#9878F8", "#F878F8", "#F85898", "#F87858", "#FCA044",
    "#F8B800", "#B8F818", "#58D854", "#58F898", "#00E8D8", "#787878", "#000000", "#000000",
    "#F8F8F8", "#A4E4FC", "#B8B8F8", "#D8B8F8", "#F8B8F8", "#F8A4C0", "#F0D0B0", "#FCE0A4",
    "#F8D878", "#D8F8A0", "#B8F8B8", "#B8F8D8", "#00FCFC", "#F8D8F8", "#000000", "#000000"
]
NES_PAL_INT = [int(c[1:], 16) for c in NES_PAL]
CHR_TILE_CACHE = np.zeros((512,8,8), dtype=np.uint8)
frame_rendered_this_step = False

# | CONTROLLER |
joy1_state = 0x00
joy1_shift_reg = 0x00
joy1_strobe = 0
# you can edit this keymap anytime
KEY_MAP = {
    pygame.K_SPACE:  0,  # A
    pygame.K_c:      1,  # B
    pygame.K_f:      2,  # Select
    pygame.K_RETURN: 3,  # Start
    pygame.K_w:      4,  # Up
    pygame.K_s:      5,  # Down
    pygame.K_a:      6,  # Left
    pygame.K_d:      7   # Right
}

def on_key_press(event):
    global joy1_state, KEY_MAP
    if event.key in KEY_MAP:
        bit = KEY_MAP[event.key]
        joy1_state |= (1<<bit)

def on_key_release(event):
    global joy1_state, KEY_MAP
    if event.key in KEY_MAP:
        bit = KEY_MAP[event.key]
        joy1_state &= ~(1<<bit)

# funcs:
def get_p():
    return (C | (Z<<1) | (I<<2) | (D<<3) | (1<<4) | (1<<5) | (V<<6) | (N<<7))

def set_p(val):
    global C,Z,I,D,V,N
    C = val & 0b1
    Z = (val>>1) & 0b1
    I = (val>>2) & 0b1
    D = (val>>3) & 0b1
    V = (val>>6) & 0b1
    N = (val>>7) & 0b1

# ROM loader:
def load_rom():
    global PC, MEM, VRAM
    while True:
        valid_rom = False
        path2romfile = input("enter path to the .nes file: ")
        
        if os.path.exists(path2romfile):
            with open(path2romfile,"rb") as rf:
                header = rf.read(16)
                if len(header) < 16 or header[0:4] == b'NES\x1a':
                    # banks
                    PRGb = header[4]
                    CHRb = header[5]
                    # trainers
                    has_trainer = (header[6] & 0x04) != 0
                    if has_trainer: rf.read(512)
                    # PRG size
                    PRGs = PRGb * 16384
                    # PRG data
                    PRGd = rf.read(PRGs)
                    
                    if CHRb > 0:
                        # CHR-ROM
                        CHRs = CHRb * 8192
                        CHRd = rf.read(CHRs)
                        for i in range(min(CHRs, 0x2000)):
                            VRAM[i] = CHRd[i]
                    else:
                        # CHR-RAM
                        pass
                    # mappers
                    if PRGb == 1:
                        # 16KB mapper
                        for i in range(16384):
                            MEM[0x8000+i] = PRGd[i]
                            MEM[0xC000+i] = PRGd[i]
                    elif PRGb == 2:
                        # 32KB mapper
                        for i in range(16384*2):
                            MEM[0x8000+i] = PRGd[i]
                    else:
                        # CMPLX mapper
                        for i in range(min(PRGs, 0x8000)):
                            MEM[0x8000+i] = PRGd[i]
                    
                    # prepare PC by reset vector
                    lowb = MEM[0xFFFC]
                    highb = MEM[0xFFFD]
                    PC = (highb<<8) | lowb
                    
                    # log it
                    print("successfully loaded the ROM file")
                    print(f"PRG banks: {PRGb} ({PRGs//1024}KB)")
                    print(f"CHR banks: {CHRb}")
                    print(f"reset vector: ${PC:04X}")
                    print("have fun playing an NES game on python!")
                    valid_rom = True
                else:
                    print("error: invalid iNES file format")
        else:
            print("error: file not found")
        
        if valid_rom: return

def pre_decode_chr():
    global VRAM, CHR_TILE_CACHE
    for tid in range(512):
        tile_addr = tid * 16
        for row in range(8):
            p1 = VRAM[tile_addr + row]
            p2 = VRAM[tile_addr + row + 8]
            for col in range(8):
                bit_shift = 7 - col
                pixel_val = ((p1 >> bit_shift) & 1) | (((p2 >> bit_shift) & 1) << 1)
                CHR_TILE_CACHE[tid][row][col] = pixel_val

# helper funcs for instructions:
def b8(val):
    return (val) & 0xFF

def b16(val):
    return (val) & 0xFFFF

def ppu_read(cpu_addr):
    global ppu_addr_latch, ppu_addr_point, ppu_ctrl, ppu_mask, ppu_stat, ppu_data_buff
    reg = 0x2000 + (cpu_addr % 8)
    
    if reg == 0x2002:
        ret_val = ppu_stat
        ppu_stat &= 0x7F
        ppu_addr_latch = 0
        return ret_val
    elif reg == 0x2007:
        addr = ppu_addr_point & 0x3FFF
        ret_val = ppu_data_buff
        ppu_data_buff = VRAM[addr]
        if 0x3F00 <= addr <= 0x3FFF:
            if (addr & 0x0013) == 0x0010:
                addr &= ~0x0010
            ret_val = VRAM[addr]
        inc=32 if (ppu_ctrl & 0x04) else 1
        ppu_addr_point = (ppu_addr_point+inc) & 0x3FFF
        return ret_val
    return 0x00

def ppu_write(cpu_addr, val):
    global ppu_addr_latch, ppu_addr_point, ppu_ctrl, ppu_mask, ppu_stat, ppu_data_buff
    reg = 0x2000 + (cpu_addr % 8)
    
    if reg == 0x2000:
        ppu_ctrl = val
    elif reg == 0x2001:
        ppu_mask = val
    elif reg == 0x2005:
        ppu_addr_latch = 1 if ppu_addr_latch == 0 else 0
    elif reg == 0x2006:
        if ppu_addr_latch == 0:
            ppu_addr_point = ((val & 0x3F)<<8) | (ppu_addr_point & 0x00FF)
            ppu_addr_latch = 1
        else:
            ppu_addr_point = (ppu_addr_point & 0xFF00) | val
            ppu_addr_latch = 0
    elif reg == 0x2007:
        write_addr = ppu_addr_point & 0x3FFF
        if 0x3F00 <= write_addr <= 0x3FFF:
            if (write_addr & 0x0013) == 0x0010:
                write_addr &= ~0x0010
        VRAM[write_addr] = val
        inc=32 if (ppu_ctrl & 0x04) else 1
        ppu_addr_point = (ppu_addr_point+inc) & 0x3FFF

def cpu_read(addr):
    global RAM, MEM, joy1_strobe, joy1_shift_reg, joy1_state
    
    # ram
    if 0x0000 <= addr <= 0x1FFF:
        return RAM[addr % 0x0800]
    # ppu regs
    elif 0x2000 <= addr <= 0x3FFF:
        return ppu_read(addr)
    # apu and I/O regs
    elif 0x4000 <= addr <= 0x401F:
        if addr == 0x4016:
            if joy1_strobe == 1:
                joy1_shift_reg = joy1_state
            ret_bit = joy1_shift_reg & 0x01
            if joy1_strobe == 0:
                joy1_shift_reg = (joy1_shift_reg>>1) | 0x80
            return ret_bit
        return 0x00
    # prg rom
    else:
        return MEM[addr]

def cpu_write(addr, val):
    global RAM, MEM, joy1_strobe, joy1_shift_reg, joy1_state
    val &= 0xFF
    
    # ram
    if 0x0000 <= addr <= 0x1FFF:
        RAM[addr % 0x0800] = val
    # ppu regs
    elif 0x2000 <= addr <= 0x3FFF:
        ppu_write(addr, val)
    # apu and I/O regs
    elif 0x4000 <= addr <= 0x401F:
        if addr == 0x4014:
            addr = val<<8
            for i in range(256):
                sprite_byte = cpu_read(addr+i)
        elif addr == 0x4016:
            joy1_strobe = val & 0x01
            if joy1_strobe == 1:
                joy1_shift_reg = joy1_state
    # prg rom
    else:
        MEM[addr] = val

def trigger_cpu_nmi():
    global PC, S, P, RAM, cpu_cycles
    cpu_write(0x0100+S, b8(PC>>8))
    S = b8(S-1)
    cpu_write(0x0100+S, b8(PC))
    S = b8(S-1)
    stat_to_push = (P & ~0x10) | 0x20
    cpu_write(0x0100+S, stat_to_push)
    S = b8(S-1)
    P |= 0x04
    low = cpu_read(0xFFFA)
    high = cpu_read(0xFFFB)
    PC = (high<<8) | low

def render_frame():
    global VRAM, ppu_ctrl, NES_PAL_INT, surf, screen, win_s
    nametable = np.array(VRAM[0x2000:0x23C0], dtype=np.int32).reshape(30,32)
    if ppu_ctrl & 0x10:
        nametable += 256
    raw_frame_blocks = CHR_TILE_CACHE[nametable]
    px_indices = raw_frame_blocks.transpose(0,2,1,3).reshape(240,256)
    vram_arr = np.array(VRAM, dtype=np.int32)
    pal_base = 0x3F00
    col_map = np.array(NES_PAL_INT, dtype=np.int32)
    px_indices = px_indices.astype(np.int32)
    pal_addrs = np.where(px_indices != 0, pal_base+px_indices, pal_base)
    pal_slots = vram_arr[pal_addrs] & 0x3F
    final_pxs = col_map[pal_slots]
    pxs = pygame.surfarray.pixels2d(surf)
    pxs[:, :] = final_pxs.T
    del pxs
    
    scaled_surf = pygame.transform.scale(surf, (256 * win_s, 240 * win_s))
    screen.blit(scaled_surf, (0, 0))
    pygame.display.flip()

def update_ppu_timers(cpu_cycles_took):
    global frame_rendered_this_step, ppu_cycles, ppu_stat, PPU_CYCLES_PER_FRAME, VBLANK_START_PPU, ppu_ctrl
    ppu_cycles += (cpu_cycles_took * 3)
    
    if ppu_cycles >= PPU_CYCLES_PER_FRAME:
        ppu_cycles -= PPU_CYCLES_PER_FRAME
        ppu_stat &= 0x7F
        render_frame()
        frame_rendered_this_step = True
    elif ppu_cycles >= VBLANK_START_PPU:
        if not (ppu_stat & 0x80):
            ppu_stat |= 0x80
            if ppu_ctrl & 0x80:
                trigger_cpu_nmi()

def inc_PC(val=1):
    global PC
    PC = b16(PC+val)

def ginc_PC(val=1):
    global PC
    return b16(PC+val)

def inc_cycle(val=1):
    global cpu_cycles
    cpu_cycles += val

def addr_abs():
    global PC, cpu_cycles
    low = cpu_read(PC)
    high = cpu_read(ginc_PC())
    inc_PC(2)
    inc_cycle(2)
    return (high<<8) | low

def addr_absX():
    global PC, X, cpu_cycles, pgc
    low = cpu_read(PC)
    high = cpu_read(ginc_PC())
    inc_PC(2)
    addr = (high<<8) | low
    res = b16(addr+X)
    if (res & 0xFF00) != (PC & 0xFF00) and pgc:
        inc_cycle(3)
    else:
        inc_cycle(2)
    return res

def addr_absY():
    global PC, Y, cpu_cycles, pgc
    low = cpu_read(PC)
    high = cpu_read(ginc_PC())
    inc_PC(2)
    addr = (high<<8) | low
    res = b16(addr+Y)
    if (res & 0xFF00) != (PC & 0xFF00) and pgc:
        inc_cycle(3)
    else:
        inc_cycle(2)
    return res

def addr_ind():
    global PC, cpu_cycles
    low = cpu_read(PC)
    high = cpu_read(ginc_PC())
    inc_PC(2)
    ptr = (high<<8) | low
    if (ptr & 0x00FF) == 0x00FF:
        low = cpu_read(ptr)
        high = cpu_read(ptr & 0xFF00)
    else:
        low = cpu_read(ptr)
        high = cpu_read(b16(ptr+1))
    inc_cycle(4)
    return (high<<8) | low

def addr_indX():
    global PC, X, cpu_cycles
    base = cpu_read(PC)
    inc_PC()
    zp_addr = b8(base+X)
    low = cpu_read(zp_addr)
    high = cpu_read(b8(zp_addr+1))
    inc_cycle(5)
    return (high<<8) | low

def addr_indY():
    global PC, Y, cpu_cycles, pgc
    base = cpu_read(PC)
    inc_PC()
    low = cpu_read(base)
    high = cpu_read(b8(base+1))
    addr = (high<<8) | low
    res = b16(addr+Y)
    if (res & 0xFF00) != (PC & 0xFF00) and pgc:
        inc_cycle(6)
    else:
        inc_cycle(5)
    return res

def addr_zp():
    global PC, cpu_cycles
    addr = cpu_read(PC)
    inc_PC()
    inc_cycle()
    return addr

def addr_zpX():
    global PC, X, cpu_cycles
    addr = cpu_read(PC)
    inc_cycle(2)
    inc_PC()
    return b8(addr+X)

def addr_zpY():
    global PC, Y, cpu_cycles
    addr = cpu_read(PC)
    inc_PC()
    inc_cycle(2)
    return b8(addr+Y)

def stack_push(val):
    global S
    cpu_write(0x0100+S, val)
    S = b8(S-1)

def stack_push_16(val):
    stack_push(b8(val>>8))
    stack_push(b8(val))

def stack_pull():
    global S
    S = b8(S+1)
    return cpu_read(0x0100+S)

def stack_pull_16():
    low = stack_pull()
    high = stack_pull()
    return (high<<8) | low

def update_Z_and_N(val):
    global Z, N
    Z=1 if val == 0 else 0
    N=1 if (val & 0x80) != 0 else 0

def jmpoffset_8bitsigned(offset):
    global PC
    old_PC = PC
    if offset & 0x80:
        soffset = offset - 256
    else:
        soffset = offset
    PC = b16(PC + soffset)
    if (old_PC & 0xFF00) != (PC & 0xFF00):
        inc_cycle(2)
    else:
        inc_cycle(1)

def pgcoff():
    global pgc
    pgc = 0

# legal pre-instructions:
def ORA(taddr):
    global A
    data = cpu_read(taddr)
    A |= data
    update_Z_and_N(A)

def ASL(taddr):
    global C
    data = cpu_read(taddr)
    C = (data>>7) & 0b1
    res = b8(data<<1)
    cpu_write(taddr, res)
    update_Z_and_N(res)
    pgcoff()
    inc_cycle(2)

def AND(taddr):
    global A
    data = cpu_read(taddr)
    A &= data
    update_Z_and_N(A)

def BIT(taddr):
    global A, Z, N, V
    data = cpu_read(taddr)
    Z=1 if (A & data) == 0 else 0
    N = (data>>7) & 0b1
    V = (data>>6) & 0b1

def ROL(taddr):
    global C
    data = cpu_read(taddr)
    old_C = C
    C = (data>>7) & 0b1
    res = b8((data<<1) | old_C)
    cpu_write(taddr, res)
    update_Z_and_N(res)
    pgcoff()
    inc_cycle(2)

def EOR(taddr):
    global A
    data = cpu_read(taddr)
    A ^= data
    update_Z_and_N(A)

def LSR(taddr):
    global C
    data = cpu_read(taddr)
    C = data & 1
    res = b8(data >> 1)
    cpu_write(taddr, res)
    update_Z_and_N(res)
    pgcoff()
    inc_cycle(2)

def JMP(taddr):
    global PC
    PC = taddr

def ADC(taddr):
    global A, C, V
    data = cpu_read(taddr)
    res = A+data+C
    V=1 if ((A^res) & (data^res) & 0x80) else 0
    C=1 if res > 0xFF else 0
    A = b8(res)
    update_Z_and_N(A)

def STA(taddr):
    global A, cpu_cycles, pgc
    cpu_write(taddr, A)
    if not pgc: cpu_cycles += 1

def STX(taddr):
    global X, cpu_cycles, pgc
    cpu_write(taddr, X)
    if not pgc: cpu_cycles += 1

def STY(taddr):
    global Y, cpu_cycles, pgc
    cpu_write(taddr, Y)
    if not pgc: cpu_cycles += 1

def LDA(taddr):
    global A
    A = cpu_read(taddr)
    update_Z_and_N(A)

def LDX(taddr):
    global X
    X = cpu_read(taddr)
    update_Z_and_N(X)

def LDY(taddr):
    global Y
    Y = cpu_read(taddr)
    update_Z_and_N(Y)

def CMP(taddr):
    global A, C
    data = b8(cpu_read(taddr))
    val = b8(A)
    res = b8(val-data)
    C=1 if val >= data else 0
    update_Z_and_N(res)

def CPX(taddr):
    global X, C
    data = b8(cpu_read(taddr))
    val = b8(X)
    res = b8(val-data)
    C=1 if val >= data else 0
    update_Z_and_N(res)

def CPY(taddr):
    global Y, C
    data = b8(cpu_read(taddr))
    val = b8(Y)
    res = b8(val-data)
    C=1 if val >= data else 0
    update_Z_and_N(res)

def DEC(taddr):
    data = cpu_read(taddr)
    res = b8(data-1)
    cpu_write(taddr, res)
    update_Z_and_N(res)
    pgcoff()
    inc_cycle(2)

def SBC(taddr):
    global A, C, V
    data = cpu_read(taddr)
    inverted = data ^ 0xFF
    res = A+inverted+C
    V=1 if ((A^res) & (inverted^res) & 0x80) else 0
    C=1 if res > 255 else 0
    A = b8(res)
    update_Z_and_N(A)

def INC(taddr):
    data = cpu_read(taddr)
    res = b8(data+1)
    cpu_write(taddr, res)
    update_Z_and_N(res)
    pgcoff()
    inc_cycle(2)

def ROR(taddr):
    global C
    data = cpu_read(taddr)
    old_C = C
    C = data & 0b1
    res = b8((data>>1) | (old_C<<7))
    cpu_write(taddr, res)
    update_Z_and_N(res)
    inc_cycle(2)

# illegal pre-instructions:
def LAX(taddr):
    global A, X
    data = cpu_read(taddr)
    A = data
    X = data
    update_Z_and_N(data)

def SAX(taddr):
    global A, X
    res = A & X
    cpu_write(taddr, res)

def DCP(taddr):
    global C
    val = cpu_read(taddr)
    dec = b8(val-1)
    cpu_write(taddr, dec)
    res = b8(A-dec)
    C=1 if A >= dec else 0
    update_Z_and_N(res)

def ISC(taddr):
    val = cpu_read(taddr)
    inc = b8(val+1)
    cpu_write(taddr, inc)
    SBC(taddr)

def SLO(taddr):
    global C, A
    val = cpu_read(taddr)
    C=1 if (val & 0x80) != 0 else 0
    shifted = b8(val<<1)
    cpu_write(taddr, shifted)
    A |= shifted
    update_Z_and_N(A)

def RLA(taddr):
    global C, A
    val = cpu_read(taddr)
    old_C = C
    C=1 if (val & 0x80) != 0 else 0
    rot = b8((val<<1) | old_C)
    cpu_write(taddr, rot)
    A &= rot
    update_Z_and_N(A)

def SRE(taddr):
    global C, A
    val = cpu_read(taddr)
    C=1 if (val & 0b1) != 0 else 0
    shifted = val>>1
    cpu_write(taddr, shifted)
    A ^= shifted
    update_Z_and_N(A)

def RRA(taddr):
    global C
    val = cpu_read(taddr)
    old_C = 0x80 if C else 0
    C=1 if (val & 0b1) != 0 else 0
    rot = (val>>1) | old_C
    cpu_write(taddr, rot)
    ADC(taddr)

# legal instructions:
def BRK(): #00
    global PC, I
    inc_PC()
    stack_push_16(PC)
    p_to_push = get_p() | 0x10
    stack_push(p_to_push)
    I=1
    lowb = cpu_read(0xFFFE)
    highb = cpu_read(0xFFFF)
    PC = (highb<<8) | lowb

def ORA_IND_X(): #01
    taddr = addr_indX()
    ORA(taddr)

def ORA_ZP(): #05
    taddr = addr_zp()
    ORA(taddr)

def ASL_ZP(): #06
    pgcoff()
    taddr = addr_zp()
    ASL(taddr)

def PHP(): #08
    p_to_push = get_p() | 0x10 | 0x20
    stack_push(p_to_push)
    inc_cycle(2)

def ORA_IMM(): #09
    global A, PC
    data = cpu_read(PC)
    inc_PC()
    A |= data
    update_Z_and_N(A)

def ASL_A(): #0A
    global A, C
    C = (A>>7) & 0b1
    A = b8(A<<1)
    update_Z_and_N(A)

def ORA_ABS(): #0D
    taddr = addr_abs()
    ORA(taddr)

def ASL_ABS(): #0E
    pgcoff()
    taddr = addr_abs()
    ASL(taddr)

def BPL(): #10
    global PC, N
    offset = cpu_read(PC)
    inc_PC()
    if not N: jmpoffset_8bitsigned(offset)
    else: inc_cycle(1)

def ORA_IND_Y(): #11
    taddr = addr_indY()
    ORA(taddr)

def ORA_ZP_X(): #15
    taddr = addr_zpX()
    ORA(taddr)

def ASL_ZP_X(): #16
    pgcoff()
    taddr = addr_zpX()
    ASL(taddr)

def CLC(): #18
    global C
    C = 0
    inc_cycle(1)

def ORA_ABS_Y(): #19
    taddr = addr_absY()
    ORA(taddr)

def ORA_ABS_X(): #1D
    taddr = addr_absX()
    ORA(taddr)

def ASL_ABS_X(): #1E
    pgcoff()
    taddr = addr_absX()
    ASL(taddr)

def JSR(): #20
    global PC
    taddr = addr_abs()
    ret_addr = b16(PC-1)
    stack_push_16(ret_addr)
    PC = taddr
    inc_cycle(4)

def AND_IND_X(): #21
    taddr = addr_indX()
    AND(taddr)

def BIT_ZP(): #24
    taddr = addr_zp()
    BIT(taddr)

def AND_ZP(): #25
    taddr = addr_zp()
    AND(taddr)

def ROL_ZP(): #26
    taddr = addr_zp()
    ROL(taddr)

def PLP(): #28
    stat_byte = stack_pull()
    set_p(stat_byte)
    inc_cycle(3)

def AND_IMM(): #29
    global A, PC
    data = cpu_read(PC)
    inc_PC()
    A &= data
    update_Z_and_N(A)

def ROL_A(): #2A
    global A, C
    old_C = C
    C = (A>>7) & 0b1
    A = b8((A<<1) | old_C)
    update_Z_and_N(A)

def BIT_ABS(): #2C
    taddr = addr_abs()
    BIT(taddr)

def AND_ABS(): #2D
    taddr = addr_abs()
    AND(taddr)

def ROL_ABS(): #2E
    pgcoff()
    taddr = addr_abs()
    ROL(taddr)

def BMI(): #30
    global PC, N
    offset = cpu_read(PC)
    inc_PC()
    if N: jmpoffset_8bitsigned(offset)
    else: inc_cycle(1)

def AND_IND_Y(): #31
    taddr = addr_indY()
    AND(taddr)

def AND_ZP_X(): #35
    taddr = addr_zpX()
    AND(taddr)

def ROL_ZP_X(): #36
    pgcoff()
    taddr = addr_zpX()
    ROL(taddr)

def SEC(): #38
    global C
    C = 1
    inc_cycle(1)

def AND_ABS_Y(): #39
    taddr = addr_absY()
    AND(taddr)

def AND_ABS_X(): #3D
    taddr = addr_absX()
    AND(taddr)

def ROL_ABS_X(): #3E
    taddr = addr_absX()
    ROL(taddr)

def RTI(): #40
    global PC
    stat_byte = stack_pull()
    set_p(stat_byte)
    PC = stack_pull_16()
    inc_cycle(5)

def EOR_IND_X(): #41
    taddr = addr_indX()
    EOR(taddr)

def EOR_ZP(): #45
    taddr = addr_zp()
    EOR(taddr)

def LSR_ZP(): #46
    pgcoff()
    taddr = addr_zp()
    LSR(taddr)

def PHA(): #48
    global A
    stack_push(A)
    inc_cycle(2)

def EOR_IMM(): #49
    global A, PC
    data = cpu_read(PC)
    inc_PC()
    A ^= data
    update_Z_and_N(A)

def LSR_A(): #4A
    global A, C
    C = A & 0b1
    A >>= 1
    update_Z_and_N(A)

def JMP_ABS(): #4C
    taddr = addr_abs()
    JMP(taddr)

def EOR_ABS(): #4D
    taddr = addr_abs()
    EOR(taddr)

def LSR_ABS(): #4E
    pgcoff()
    taddr = addr_abs()
    LSR(taddr)

def BVC(): #50
    global PC, V
    offset = cpu_read(PC)
    inc_PC()
    if not V: jmpoffset_8bitsigned(offset)
    else: inc_cycle(1)

def EOR_IND_Y(): #51
    taddr = addr_indY()
    EOR(taddr)

def EOR_ZP_X(): #55
    taddr = addr_zpX()
    EOR(taddr)

def LSR_ZP_X(): #56
    pgcoff()
    taddr = addr_zpX()
    LSR(taddr)

def CLI(): #58
    global I
    I = 0
    inc_cycle(1)

def EOR_ABS_Y(): #59
    taddr = addr_absY()
    EOR(taddr)

def EOR_ABS_X(): #5D
    taddr = addr_absX()
    EOR(taddr)

def LSR_ABS_X(): #5E
    pgcoff()
    taddr = addr_absX()
    LSR(taddr)

def RTS(): #60
    global PC
    ret_addr = stack_pull_16()
    PC = b16(ret_addr+1)
    inc_cycle(5)

def ADC_IND_X(): #61
    taddr = addr_indX()
    ADC(taddr)

def ADC_ZP(): #65
    taddr = addr_zp()
    ADC(taddr)

def ROR_ZP(): #66
    pgcoff()
    taddr = addr_zp()
    ROR(taddr)

def PLA(): #68
    global A
    A = stack_pull()
    update_Z_and_N(A)
    inc_cycle(3)

def ADC_IMM(): #69
    global PC
    ADC(PC)
    inc_PC()

def ROR_A(): #6A
    global A, C
    old_C = C
    C = A & 0b1
    A = b8((A>>1) | (old_C<<7))
    update_Z_and_N(A)

def JMP_IND(): #6C
    taddr = addr_ind()
    JMP(taddr)

def ADC_ABS(): #6D
    taddr = addr_abs()
    ADC(taddr)

def ROR_ABS(): #6E
    pgcoff()
    taddr = addr_abs()
    ROR(taddr)

def BVS(): #70
    global PC, V
    offset = cpu_read(PC)
    inc_PC()
    if V: jmpoffset_8bitsigned(offset)
    else: inc_cycle(1)

def ADC_IND_Y(): #71
    taddr = addr_indY()
    ADC(taddr)

def ADC_ZP_X(): #75
    taddr = addr_zpX()
    ADC(taddr)

def ROR_ZP_X(): #76
    pgcoff()
    taddr = addr_zpX()
    ROR(taddr)

def SEI(): #78
    global I
    I = 1
    inc_cycle(1)

def ADC_ABS_Y(): #79
    taddr = addr_absY()
    ADC(taddr)

def ADC_ABS_X(): #7D
    taddr = addr_absX()
    ADC(taddr)

def ROR_ABS_X(): #7E
    pgcoff()
    taddr = addr_absX()
    ROR(taddr)

def STA_IND_X(): #81
    taddr = addr_indX()
    STA(taddr)

def STY_ZP(): #84
    taddr = addr_zp()
    STY(taddr)

def STA_ZP(): #85
    taddr = addr_zp()
    STA(taddr)

def STX_ZP(): #86
    taddr = addr_zp()
    STX(taddr)

def DEY(): #88
    global Y
    Y = b8(Y-1)
    update_Z_and_N(Y)
    inc_cycle(1)

def TXA(): #8A
    global X, A
    A = X
    update_Z_and_N(A)
    inc_cycle(1)

def STY_ABS(): #8C
    taddr = addr_abs()
    STY(taddr)

def STA_ABS(): #8D
    taddr = addr_abs()
    STA(taddr)

def STX_ABS(): #8E
    taddr = addr_abs()
    STX(taddr)

def BCC(): #90
    global PC, C
    offset = cpu_read(PC)
    inc_PC()
    if not C: jmpoffset_8bitsigned(offset)
    else: inc_cycle(1)

def STA_IND_Y(): #91
    taddr = addr_indY()
    STA(taddr)

def STY_ZP_X(): #94
    taddr = addr_zpX()
    STY(taddr)

def STA_ZP_X(): #95
    taddr = addr_zpX()
    STA(taddr)

def STX_ZP_Y(): #96
    taddr = addr_zpY()
    STY(taddr)

def TYA(): #98
    global Y, A
    A = Y
    update_Z_and_N(A)
    inc_cycle(1)

def STA_ABS_Y(): #99
    taddr = addr_absY()
    STA(taddr)

def TXS(): #9A
    global X, S
    S = X
    inc_cycle(1)

def STA_ABS_X(): #9D
    taddr = addr_absX()
    STA(taddr)

def LDY_IMM(): #A0
    global PC
    LDY(PC)
    inc_PC()

def LDA_IND_X(): #A1
    taddr = addr_indX()
    LDA(taddr)

def LDX_IMM(): #A2
    global PC
    LDX(PC)
    inc_PC()

def LDY_ZP(): #A4
    taddr = addr_zp()
    LDY(taddr)

def LDA_ZP(): #A5
    taddr = addr_zp()
    LDA(taddr)

def LDX_ZP(): #A6
    taddr = addr_zp()
    LDX(taddr)

def TAY(): #A8
    global A, Y
    Y = A
    update_Z_and_N(Y)
    inc_cycle(1)

def LDA_IMM(): #A9
    global PC
    LDA(PC)
    inc_PC()

def TAX(): #AA
    global A, X
    X = A
    update_Z_and_N(X)
    inc_cycle(1)

def LDY_ABS(): #AC
    taddr = addr_abs()
    LDY(taddr)

def LDA_ABS(): #AD
    taddr = addr_abs()
    LDA(taddr)

def LDX_ABS(): #AE
    taddr = addr_abs()
    LDX(taddr)

def BCS(): #B0
    global PC, C
    offset = cpu_read(PC)
    inc_PC()
    if C: jmpoffset_8bitsigned(offset)

def LDA_IND_Y(): #B1
    taddr = addr_indY()
    LDA(taddr)

def LDY_ZP_X(): #B4
    taddr = addr_zpX()
    LDY(taddr)

def LDA_ZP_X(): #B5
    taddr = addr_zpX()
    LDA(taddr)

def LDX_ZP_Y(): #B6
    taddr = addr_zpY()
    LDX(taddr)

def CLV(): #B8
    global V
    V = 0
    inc_cycle(1)

def LDA_ABS_Y(): #B9
    taddr = addr_absY()
    LDA(taddr)

def TSX(): #BA
    global S, X
    X = S
    update_Z_and_N(X)
    inc_cycle(1)

def LDY_ABS_X(): #BC
    taddr = addr_absX()
    LDY(taddr)

def LDA_ABS_X(): #BD
    taddr = addr_absX()
    LDA(taddr)

def LDX_ABS_Y(): #BE
    taddr = addr_absY()
    LDX(taddr)

def CPY_IMM(): #C0
    global PC
    CPY(PC)
    inc_PC()

def CMP_IND_X(): #C1
    taddr = addr_indX()
    CMP(taddr)

def CPY_ZP(): #C4
    taddr = addr_zp()
    CPY(taddr)

def CMP_ZP(): #C5
    taddr = addr_zp()
    CMP(taddr)

def DEC_ZP(): #C6
    pgcoff()
    taddr = addr_zp()
    DEC(taddr)

def INY(): #C8
    global Y
    Y = b8(Y+1)
    update_Z_and_N(Y)
    inc_cycle(1)

def CMP_IMM(): #C9
    global PC
    CMP(PC)
    inc_PC()

def DEX(): #CA
    global X
    X = b8(X-1)
    update_Z_and_N(X)
    inc_cycle(1)

def CPY_ABS(): #CC
    taddr = addr_abs()
    CPY(taddr)

def CMP_ABS(): #CD
    taddr = addr_abs()
    CMP(taddr)

def DEC_ABS(): #CE
    pgcoff()
    taddr = addr_abs()
    DEC(taddr)

def BNE(): #D0
    global PC, Z
    offset = cpu_read(PC)
    inc_PC()
    if not Z: jmpoffset_8bitsigned(offset)

def CMP_IND_Y(): #D1
    taddr = addr_indY()
    CMP(taddr)

def CMP_ZP_X(): #D5
    taddr = addr_zpX()
    CMP(taddr)

def DEC_ZP_X(): #D6
    pgcoff()
    taddr = addr_zpX()
    DEC(taddr)

def CLD(): #D8
    global D
    D = 0
    inc_cycle(1)

def CMP_ABS_Y(): #D9
    taddr = addr_absY()
    CMP(taddr)

def CMP_ABS_X(): #DD
    taddr = addr_absX()
    CMP(taddr)

def DEC_ABS_X(): #DE
    pgcoff()
    taddr = addr_absX()
    DEC(taddr)

def CPX_IMM(): #E0
    global PC
    CPX(PC)
    inc_PC()

def SBC_IND_X(): #E1
    taddr = addr_indX()
    SBC(taddr)

def CPX_ZP(): #E4
    taddr = addr_zp()
    CPX(taddr)

def SBC_ZP(): #E5
    taddr = addr_zp()
    SBC(taddr)

def INC_ZP(): #E6
    pgcoff()
    taddr = addr_zp()
    INC(taddr)

def INX(): #E8
    global X
    X = b8(X+1)
    update_Z_and_N(X)
    inc_cycle(1)

def SBC_IMM(): #E9
    global PC
    SBC(PC)
    inc_PC()

def NOP(): #EA
    pass # do nothing lol

def CPX_ABS(): #EC
    taddr = addr_abs()
    CPX(taddr)

def SBC_ABS(): #ED
    taddr = addr_abs()
    SBC(taddr)

def INC_ABS(): #EE
    pgcoff()
    taddr = addr_abs()
    INC(taddr)

def BEQ(): #F0
    global PC, Z
    offset = cpu_read(PC)
    inc_PC()
    if Z: jmpoffset_8bitsigned(offset)
    else: inc_cycle(1)

def SBC_IND_Y(): #F1
    taddr = addr_indY()
    SBC(taddr)

def SBC_ZP_X(): #F5
    taddr = addr_zpX()
    SBC(taddr)

def INC_ZP_X(): #F6
    pgcoff()
    taddr = addr_zpX()
    INC(taddr)

def SED(): #F8
    global D
    D = 1
    inc_cycle(1)

def SBC_ABS_Y(): #F9
    taddr = addr_absY()
    SBC(taddr)

def SBC_ABS_X(): #FD
    taddr = addr_absX()
    SBC(taddr)

def INC_ABS_X(): #FE
    pgcoff()
    taddr = addr_absX()
    INC(taddr)

# illegal instructions:
def LAX_IND_X(): #A3
    taddr = addr_indX()
    LAX(taddr)

def LAX_ZP(): #A7
    taddr = addr_zp()
    LAX(taddr)

def LAX_ZP_Y(): #B7
    taddr = addr_zpY()
    LAX(taddr)

def LAX_ABS(): #AF
    taddr = addr_abs()
    LAX(taddr)

def LAX_ABS_Y(): #BF
    taddr = addr_absY()
    LAX(taddr)

def LAX_IND_Y(): #B3
    taddr = addr_indY()
    LAX(taddr)

def SAX_IND_X(): #83
    taddr = addr_indX()
    SAX(taddr)

def SAX_ZP(): #87
    taddr = addr_zp()
    SAX(taddr)

def SAX_ZP_Y(): #97
    taddr = addr_zpY()
    SAX(taddr)

def SAX_ABS(): #8F
    taddr = addr_abs()
    SAX(taddr)

def SBC_IMM(): #EB
    global PC
    SBC(PC)
    inc_PC()

def DCP_IND_X(): #C3
    taddr = addr_indX()
    DCP(taddr)

def DCP_ZP(): #C7
    taddr = addr_zp()
    DCP(taddr)

def DCP_ZP_Y(): #D7
    taddr = addr_zpY()
    DCP(taddr)

def DCP_ABS(): #CF
    taddr = addr_abs()
    DCP(taddr)

def DCP_ABS_X(): #DF
    taddr = addr_absX()
    DCP(taddr)

def DCP_ABS_Y(): #DB
    taddr = addr_absY()
    DCP(taddr)

def DCP_IND_Y(): #D3
    taddr = addr_indY()
    DCP(taddr)

def ISC_IND_X(): #E3
    taddr = addr_indX()
    ISC(taddr)

def ISC_ZP(): #E7
    taddr = addr_zp()
    ISC(taddr)

def ISC_ZP_X(): #F7
    taddr = addr_zpX()
    ISC(taddr)

def ISC_ABS(): #EF
    taddr = addr_abs()
    ISC(taddr)

def ISC_ABS_X(): #FF
    taddr = addr_absX()
    ISC(taddr)

def ISC_ABS_Y(): #FB
    taddr = addr_absY()
    ISC(taddr)

def ISC_IND_Y(): #F3
    taddr = addr_indY()
    ISC(taddr)

def SLO_IND_X(): #03
    taddr = addr_indX()
    SLO(taddr)

def SLO_ZP(): #07
    taddr = addr_zp()
    SLO(taddr)

def SLO_ZP_X(): #17
    taddr = addr_zpX()
    SLO(taddr)

def SLO_ABS(): #0F
    taddr = addr_abs()
    SLO(taddr)

def SLO_ABS_X(): #1F
    taddr = addr_absX()
    SLO(taddr)

def SLO_ABS_Y(): #1B
    taddr = addr_absY()
    SLO(taddr)

def SLO_IND_Y(): #13
    taddr = addr_indY()
    SLO(taddr)

def RLA_IND_X(): #23
    taddr = addr_indX()
    RLA(taddr)

def RLA_ZP(): #27
    taddr = addr_zp()
    RLA(taddr)

def RLA_ZP_X(): #37
    taddr = addr_zpX()
    RLA(taddr)

def RLA_ABS(): #2F
    taddr = addr_abs()
    RLA(taddr)

def RLA_ABS_X(): #3F
    taddr = addr_absX()
    RLA(taddr)

def RLA_ABS_Y(): #3B
    taddr = addr_absY()
    RLA(taddr)

def RLA_IND_Y(): #33
    taddr = addr_indY()
    RLA(taddr)

def SRE_IND_X(): #43
    taddr = addr_indX()
    SRE(taddr)

def SRE_ZP(): #47
    taddr = addr_zp()
    SRE(taddr)

def SRE_ZP_X(): #57
    taddr = addr_zpX()
    SRE(taddr)

def SRE_ABS(): #4F
    taddr = addr_abs()
    SRE(taddr)

def SRE_ABS_X(): #5F
    taddr = addr_absX()
    SRE(taddr)

def SRE_ABS_Y(): #5B
    taddr = addr_absY()
    SRE(taddr)

def SRE_IND_Y(): #53
    taddr = addr_indY()
    SRE(taddr)

def RRA_IND_X(): #63
    taddr = addr_indX()
    RRA(taddr)

def RRA_ZP(): #67
    taddr = addr_zp()
    RRA(taddr)

def RRA_ZP_X(): #77
    taddr = addr_zpX()
    RRA(taddr)

def RRA_ABS(): #6F
    taddr = addr_abs()
    RRA(taddr)

def RRA_ABS_X(): #7F
    taddr = addr_absX()
    RRA(taddr)

def RRA_ABS_Y(): #7B
    taddr = addr_absY()
    RRA(taddr)

def RRA_IND_Y(): #73
    taddr = addr_indY()
    RRA(taddr)

# the cpu itself:
instructions = {
    # legal opcodes:
    0x00: 'BRK',
    0x01: 'ORA-IND,X',
    0x05: 'ORA-ZP',
    0x06: 'ASL-ZP',
    0x08: 'PHP',
    0x09: 'ORA-IMM',
    0x0A: 'ASL-A',
    0x0D: 'ORA-ABS',
    0x0E: 'ASL-ABS',
    0x10: 'BPL',
    0x11: 'ORA-IND,Y',
    0x15: 'ORA-ZP,X',
    0x16: 'ASL-ZP,X',
    0x18: 'CLC',
    0x19: 'ORA-ABS,Y',
    0x1D: 'ORA-ABS,X',
    0x1E: 'ASL-ABS,X',
    0x20: 'JSR',
    0x21: 'AND-IND,X',
    0x24: 'BIT-ZP',
    0x25: 'AND-ZP',
    0x26: 'ROL-ZP',
    0x28: 'PLP',
    0x29: 'AND-IMM',
    0x2A: 'ROL-A',
    0x2C: 'BIT-ABS',
    0x2D: 'AND-ABS',
    0x2E: 'ROL-ABS',
    0x30: 'BMI',
    0x31: 'AND-IND,Y',
    0x35: 'AND-ZP,X',
    0x36: 'ROL-ZP,X',
    0x38: 'SEC',
    0x39: 'AND-ABS,Y',
    0x3D: 'AND-ABS,X',
    0x3E: 'ROL-ABS,X',
    0x40: 'RTI',
    0x41: 'EOR-IND,X',
    0x45: 'EOR-ZP',
    0x46: 'LSR-ZP',
    0x48: 'PHA',
    0x49: 'EOR-IMM',
    0x4A: 'LSR-A',
    0x4C: 'JMP-ABS',
    0x4D: 'EOR-ABS',
    0x4E: 'LSR-ABS',
    0x50: 'BVC',
    0x51: 'EOR-IND,Y',
    0x54: 'NOP-ZP,X',
    0x55: 'EOR-ZP,X',
    0x56: 'LSR-ZP,X',
    0x58: 'CLI',
    0x59: 'EOR-ABS,Y',
    0x5D: 'EOR-ABS,X',
    0x5E: 'LSR-ABS,X',
    0x60: 'RTS',
    0x61: 'ADC-IND,X',
    0x65: 'ADC-ZP',
    0x66: 'ROR-ZP',
    0x68: 'PLA',
    0x69: 'ADC-IMM',
    0x6A: 'ROR-A',
    0x6C: 'JMP-IND',
    0x6D: 'ADC-ABS',
    0x6E: 'ROR-ABS',
    0x70: 'BVS',
    0x71: 'ADC-IND,Y',
    0x74: 'NOP-ZP,X',
    0x75: 'ADC-ZP,X',
    0x76: 'ROR-ZP,X',
    0x78: 'SEI',
    0x79: 'ADC-ABS,Y',
    0x7D: 'ADC-ABS,X',
    0x7E: 'ROR-ABS,X',
    0x81: 'STA-IND,X',
    0x84: 'STY-ZP',
    0x85: 'STA-ZP',
    0x86: 'STX-ZP',
    0x88: 'DEY',
    0x8A: 'TXA',
    0x8C: 'STY-ABS',
    0x8D: 'STA-ABS',
    0x8E: 'STX-ABS',
    0x90: 'BCC',
    0x91: 'STA-IND,Y',
    0x94: 'STY-ZP,X',
    0x95: 'STA-ZP,X',
    0x96: 'STX-ZP,Y',
    0x98: 'TYA',
    0x99: 'STA-ABS,Y',
    0x9A: 'TXS',
    0x9D: 'STA-ABS,X',
    0xA0: 'LDY-IMM',
    0xA1: 'LDA-IND,X',
    0xA2: 'LDX-IMM',
    0xA4: 'LDY-ZP',
    0xA5: 'LDA-ZP',
    0xA6: 'LDX-ZP',
    0xA8: 'TAY',
    0xA9: 'LDA-IMM',
    0xAA: 'TAX',
    0xAC: 'LDY-ABS',
    0xAD: 'LDA-ABS',
    0xAE: 'LDX-ABS',
    0xB0: 'BCS',
    0xB1: 'LDA-IND,Y',
    0xB4: 'LDY-ZP,X',
    0xB5: 'LDA-ZP,X',
    0xB6: 'LDX-ZP,Y',
    0xB8: 'CLV',
    0xB9: 'LDA-ABS,Y',
    0xBA: 'TSX',
    0xBC: 'LDY-ABS,X',
    0xBD: 'LDA-ABS,X',
    0xBE: 'LDX-ABS,Y',
    0xC0: 'CPY-IMM',
    0xC1: 'CMP-IND,X',
    0xC4: 'CPY-ZP',
    0xC5: 'CMP-ZP',
    0xC6: 'DEC-ZP',
    0xC8: 'INY',
    0xC9: 'CMP-IMM',
    0xCA: 'DEX',
    0xCC: 'CPY-ABS',
    0xCD: 'CMP-ABS',
    0xCE: 'DEC-ABS',
    0xD0: 'BNE',
    0xD1: 'CMP-IND,Y',
    0xD5: 'CMP-ZP,X',
    0xD6: 'DEC-ZP,X',
    0xD8: 'CLD',
    0xD9: 'CMP-ABS,Y',
    0xDD: 'CMP-ABS,X',
    0xDE: 'DEC-ABS,X',
    0xE0: 'CPX-IMM',
    0xE1: 'SBC-IND,X',
    0xE4: 'CPX-ZP',
    0xE5: 'SBC-ZP',
    0xE6: 'INC-ZP',
    0xE8: 'INX',
    0xE9: 'SBC-IMM',
    0xEA: 'NOP',
    0xEC: 'CPX-ABS',
    0xED: 'SBC-ABS',
    0xEE: 'INC-ABS',
    0xF0: 'BEQ',
    0xF1: 'SBC-IND,Y',
    0xF5: 'SBC-ZP,X',
    0xF6: 'INC-ZP,X',
    0xF8: 'SED',
    0xF9: 'SBC-ABS,Y',
    0xFD: 'SBC-ABS,X',
    0xFE: 'INC-ABS,X',
    
    # illegal opcodes:
    0x04: 'NOP-ZP',
    0x0C: 'NOP-ABS',
    **{op: 'NOP' for op in [0x1A, 0x3A, 0x5A, 0x7A, 0xDA, 0xFA]},
    **{op: 'NOP-ZP,X' for op in [0x14, 0x34, 0x44, 0x54, 0x64, 0x74, 0xD4, 0xF4]},
    **{op: 'NOP-ABS,X' for op in [0x1C, 0x3C, 0x5C, 0x7C, 0xDC, 0xFC]},
    **{op: 'NOP-IMM' for op in [0x80, 0x82, 0x89, 0xC2, 0xE2]},
    0xA3: 'LAX-IND,X',
    0xA7: 'LAX-ZP',
    0xB7: 'LAX-ZP,Y',
    0xAF: 'LAX-ABS',
    0xBF: 'LAX-ABS,Y',
    0xB3: 'LAX-IND,Y',
    0x83: 'SAX-IND,X',
    0x87: 'SAX-ZP',
    0x97: 'SAX-ZP,Y',
    0x8F: 'SAX-ABS',
    0xEB: 'SBC-IMM',
    0xC3: 'DCP-IND,X',
    0xC7: 'DCP-ZP',
    0xD7: 'DCP-ZP,Y',
    0xCF: 'DCP-ABS',
    0xDF: 'DCP-ABS,X',
    0xDB: 'DCP-ABS,Y',
    0xD3: 'DCP-IND,Y',
    0xE3: 'ISC-IND,X',
    0xE7: 'ISC-ZP',
    0xF7: 'ISC-ZP,X',
    0xEF: 'ISC-ABS',
    0xFF: 'ISC-ABS,X',
    0xFB: 'ISC-ABS,Y',
    0xF3: 'ISC-IND,Y',
    0x03: 'SLO-IND,X',
    0x07: 'SLO-ZP',
    0x17: 'SLO-ZP,X',
    0x0F: 'SLO-ABS',
    0x1F: 'SLO-ABS,X',
    0x1B: 'SLO-ABS,Y',
    0x13: 'SLO-IND,Y',
    0x23: 'RLA-IND,X',
    0x27: 'RLA-ZP',
    0x37: 'RLA-ZP,X',
    0x2F: 'RLA-ABS',
    0x3F: 'RLA-ABS,X',
    0x3B: 'RLA-ABS,Y',
    0x33: 'RLA-IND,Y',
    0x43: 'SRE-IND,X',
    0x47: 'SRE-ZP',
    0x57: 'SRE-ZP,X',
    0x4F: 'SRE-ABS',
    0x5F: 'SRE-ABS,X',
    0x5B: 'SRE-ABS,Y',
    0x53: 'SRE-IND,Y',
    0x63: 'RRA-IND,X',
    0x67: 'RRA-ZP',
    0x77: 'RRA-ZP,X',
    0x6F: 'RRA-ABS',
    0x7F: 'RRA-ABS,X',
    0x7B: 'RRA-ABS,Y',
    0x73: 'RRA-IND,Y',
    
}

def isoc(id):
    global opcode
    return opcode == id

def getop(id):
    global opcode
    try:
        return instructions[id]
    except:
        return '?'

def step_cpu():
    global PC, A, X, Y, S, P, opcode, cpu_cycles, pgc, CYCLES_PER_FRAME, instruction_count
    opcode = cpu_read(PC)
    instruction_count += 1
    
    if debug_mode:
        f_n = 'N' if (P & 0x80) else '.'
        f_v = 'V' if (P & 0x40) else '.'
        f_u = 'U' if (P & 0x20) else '.'
        f_b = 'B' if (P & 0x10) else '.'
        f_d = 'D' if (P & 0x08) else '.'
        f_i = 'I' if (P & 0x04) else '.'
        f_z = 'Z' if (P & 0x02) else '.'
        f_c = 'C' if (P & 0x01) else '.'
        flag_str = f"{f_n}{f_v}{f_u}{f_b}{f_d}{f_i}{f_z}{f_c}"

        print(f'[{instruction_count}] PC=${PC:04X} / op=${opcode:02X} ({getop(opcode)}) / A=${A:02X} X=${X:02X} Y=${Y:02X} S=${S:02X} P=${P:02X} [{flag_str}]')
    
    # step forward
    inc_PC()
    how_many_cycles_took_before = cpu_cycles
    cpu_cycles += 1
    pgc = 1
    
    # ..and execute opcode i guess
    # legal opcodes:
    if isoc(0x00): BRK()
    elif isoc(0x01): ORA_IND_X()
    elif isoc(0x05): ORA_ZP()
    elif isoc(0x06): ASL_ZP()
    elif isoc(0x08): PHP()
    elif isoc(0x09): ORA_IMM()
    elif isoc(0x0A): ASL_A()
    elif isoc(0x0D): ORA_ABS()
    elif isoc(0x0E): ASL_ABS()
    elif isoc(0x10): BPL()
    elif isoc(0x11): ORA_IND_Y()
    elif isoc(0x15): ORA_ZP_X()
    elif isoc(0x16): ASL_ZP_X()
    elif isoc(0x18): CLC()
    elif isoc(0x19): ORA_ABS_Y()
    elif isoc(0x1D): ORA_ABS_X()
    elif isoc(0x1E): ASL_ABS_X()
    elif isoc(0x20): JSR()
    elif isoc(0x21): AND_IND_X()
    elif isoc(0x24): BIT_ZP()
    elif isoc(0x25): AND_ZP()
    elif isoc(0x26): ROL_ZP()
    elif isoc(0x28): PLP()
    elif isoc(0x29): AND_IMM()
    elif isoc(0x2A): ROL_A()
    elif isoc(0x2C): BIT_ABS()
    elif isoc(0x2D): AND_ABS()
    elif isoc(0x2E): ROL_ABS()
    elif isoc(0x30): BMI()
    elif isoc(0x31): AND_IND_Y()
    elif isoc(0x35): AND_ZP_X()
    elif isoc(0x36): ROL_ZP_X()
    elif isoc(0x38): SEC()
    elif isoc(0x39): AND_ABS_Y()
    elif isoc(0x3D): AND_ABS_X()
    elif isoc(0x3E): ROL_ABS_X()
    elif isoc(0x40): RTI()
    elif isoc(0x41): EOR_IND_X()
    elif isoc(0x45): EOR_ZP()
    elif isoc(0x46): LSR_ZP()
    elif isoc(0x48): PHA()
    elif isoc(0x49): EOR_IMM()
    elif isoc(0x4A): LSR_A()
    elif isoc(0x4C): JMP_ABS()
    elif isoc(0x4D): EOR_ABS()
    elif isoc(0x4E): LSR_ABS()
    elif isoc(0x50): BVC()
    elif isoc(0x51): EOR_IND_Y()
    elif isoc(0x55): EOR_ZP_X()
    elif isoc(0x56): LSR_ZP_X()
    elif isoc(0x58): CLI()
    elif isoc(0x59): EOR_ABS_Y()
    elif isoc(0x5D): EOR_ABS_X()
    elif isoc(0x5E): LSR_ABS_X()
    elif isoc(0x60): RTS()
    elif isoc(0x61): ADC_IND_X()
    elif isoc(0x65): ADC_ZP()
    elif isoc(0x66): ROR_ZP()
    elif isoc(0x68): PLA()
    elif isoc(0x69): ADC_IMM()
    elif isoc(0x6A): ROR_A()
    elif isoc(0x6C): JMP_IND()
    elif isoc(0x6D): ADC_ABS()
    elif isoc(0x6E): ROR_ABS()
    elif isoc(0x70): BVS()
    elif isoc(0x71): ADC_IND_Y()
    elif isoc(0x75): ADC_ZP_X()
    elif isoc(0x76): ROR_ZP_X()
    elif isoc(0x78): SEI()
    elif isoc(0x79): ADC_ABS_Y()
    elif isoc(0x7D): ADC_ABS_X()
    elif isoc(0x7E): ROR_ABS_X()
    elif isoc(0x81): STA_IND_X()
    elif isoc(0x84): STY_ZP()
    elif isoc(0x85): STA_ZP()
    elif isoc(0x86): STX_ZP()
    elif isoc(0x88): DEY()
    elif isoc(0x8A): TXA()
    elif isoc(0x8C): STY_ABS()
    elif isoc(0x8D): STA_ABS()
    elif isoc(0x8E): STX_ABS()
    elif isoc(0x90): BCC()
    elif isoc(0x91): STA_IND_Y()
    elif isoc(0x94): STY_ZP_X()
    elif isoc(0x95): STA_ZP_X()
    elif isoc(0x96): STX_ZP_Y()
    elif isoc(0x98): TYA()
    elif isoc(0x99): STA_ABS_Y()
    elif isoc(0x9A): TXS()
    elif isoc(0x9D): STA_ABS_X()
    elif isoc(0xA0): LDY_IMM()
    elif isoc(0xA1): LDA_IND_X()
    elif isoc(0xA2): LDX_IMM()
    elif isoc(0xA4): LDY_ZP()
    elif isoc(0xA5): LDA_ZP()
    elif isoc(0xA6): LDX_ZP()
    elif isoc(0xA8): TAY()
    elif isoc(0xA9): LDA_IMM()
    elif isoc(0xAA): TAX()
    elif isoc(0xAC): LDY_ABS()
    elif isoc(0xAD): LDA_ABS()
    elif isoc(0xAE): LDX_ABS()
    elif isoc(0xB0): BCS()
    elif isoc(0xB1): LDA_IND_Y()
    elif isoc(0xB4): LDY_ZP_X()
    elif isoc(0xB5): LDA_ZP_X()
    elif isoc(0xB6): LDX_ZP_Y()
    elif isoc(0xB8): CLV()
    elif isoc(0xB9): LDA_ABS_Y()
    elif isoc(0xBA): TSX()
    elif isoc(0xBC): LDY_ABS_X()
    elif isoc(0xBD): LDA_ABS_X()
    elif isoc(0xBE): LDX_ABS_Y()
    elif isoc(0xC0): CPY_IMM()
    elif isoc(0xC1): CMP_IND_X()
    elif isoc(0xC4): CPY_ZP()
    elif isoc(0xC5): CMP_ZP()
    elif isoc(0xC6): DEC_ZP()
    elif isoc(0xC8): INY()
    elif isoc(0xC9): CMP_IMM()
    elif isoc(0xCA): DEX()
    elif isoc(0xCC): CPY_ABS()
    elif isoc(0xCD): CMP_ABS()
    elif isoc(0xCE): DEC_ABS()
    elif isoc(0xD0): BNE()
    elif isoc(0xD1): CMP_IND_Y()
    elif isoc(0xD5): CMP_ZP_X()
    elif isoc(0xD6): DEC_ZP_X()
    elif isoc(0xD8): CLD()
    elif isoc(0xD9): CMP_ABS_Y()
    elif isoc(0xDD): CMP_ABS_X()
    elif isoc(0xDE): DEC_ABS_X()
    elif isoc(0xE0): CPX_IMM()
    elif isoc(0xE1): SBC_IND_X()
    elif isoc(0xE4): CPX_ZP()
    elif isoc(0xE5): SBC_ZP()
    elif isoc(0xE6): INC_ZP()
    elif isoc(0xE8): INX()
    elif isoc(0xE9): SBC_IMM()
    elif isoc(0xEA): NOP()
    elif isoc(0xEC): CPX_ABS()
    elif isoc(0xED): SBC_ABS()
    elif isoc(0xEE): INC_ABS()
    elif isoc(0xF0): BEQ()
    elif isoc(0xF1): SBC_IND_Y()
    elif isoc(0xF5): SBC_ZP_X()
    elif isoc(0xF6): INC_ZP_X()
    elif isoc(0xF8): SED()
    elif isoc(0xF9): SBC_ABS_Y()
    elif isoc(0xFD): SBC_ABS_X()
    elif isoc(0xFE): INC_ABS_X()
    
    # illegal opcodes:
    elif isoc(0x04): _=addr_zp(); cpu_read(_)
    elif opcode in [0x1A, 0x3A, 0x5A, 0x7A, 0xDA, 0xFA]: inc_cycle()
    elif opcode in [0x14, 0x34, 0x44, 0x54, 0x64, 0x74, 0xD4, 0xF4]: addr_zpX()
    elif isoc(0x0C): addr_abs(); inc_cycle()
    elif opcode in [0x1C, 0x3C, 0x5C, 0x7C, 0xDC, 0xFC]: addr_absX()
    elif opcode in [0x80, 0x82, 0x89, 0xC2, 0xE2]: cpu_read(PC); inc_PC()
    elif isoc(0xA3): LAX_IND_X()
    elif isoc(0xA7): LAX_ZP()
    elif isoc(0xB7): LAX_ZP_Y()
    elif isoc(0xAF): LAX_ABS()
    elif isoc(0xBF): LAX_ABS_Y()
    elif isoc(0xB3): LAX_IND_Y()
    elif isoc(0x83): SAX_IND_X()
    elif isoc(0x87): SAX_ZP()
    elif isoc(0x97): SAX_ZP_Y()
    elif isoc(0x8F): SAX_ABS()
    elif isoc(0xEB): SBC_IMM()
    elif isoc(0xC3): DCP_IND_X()
    elif isoc(0xC7): DCP_ZP()
    elif isoc(0xD7): DCP_ZP_Y()
    elif isoc(0xCF): DCP_ABS()
    elif isoc(0xDF): DCP_ABS_X()
    elif isoc(0xDB): DCP_ABS_Y()
    elif isoc(0xD3): DCP_IND_Y()
    elif isoc(0xE3): ISC_IND_X()
    elif isoc(0xE7): ISC_ZP()
    elif isoc(0xF7): ISC_ZP_X()
    elif isoc(0xEF): ISC_ABS()
    elif isoc(0xFF): ISC_ABS_X()
    elif isoc(0xFB): ISC_ABS_Y()
    elif isoc(0xF3): ISC_IND_Y()
    elif isoc(0x03): SLO_IND_X()
    elif isoc(0x07): SLO_ZP()
    elif isoc(0x17): SLO_ZP_X()
    elif isoc(0x0F): SLO_ABS()
    elif isoc(0x1F): SLO_ABS_X()
    elif isoc(0x1B): SLO_ABS_Y()
    elif isoc(0x13): SLO_IND_Y()
    elif isoc(0x23): RLA_IND_X()
    elif isoc(0x27): RLA_ZP()
    elif isoc(0x37): RLA_ZP_X()
    elif isoc(0x2F): RLA_ABS()
    elif isoc(0x3F): RLA_ABS_X()
    elif isoc(0x3B): RLA_ABS_Y()
    elif isoc(0x33): RLA_IND_Y()
    elif isoc(0x43): SRE_IND_X()
    elif isoc(0x47): SRE_ZP()
    elif isoc(0x57): SRE_ZP_X()
    elif isoc(0x4F): SRE_ABS()
    elif isoc(0x5F): SRE_ABS_X()
    elif isoc(0x5B): SRE_ABS_Y()
    elif isoc(0x53): SRE_IND_Y()
    elif isoc(0x63): RRA_IND_X()
    elif isoc(0x67): RRA_ZP()
    elif isoc(0x77): RRA_ZP_X()
    elif isoc(0x6F): RRA_ABS()
    elif isoc(0x7F): RRA_ABS_X()
    elif isoc(0x7B): RRA_ABS_Y()
    elif isoc(0x73): RRA_IND_Y()
    
    # invalid:
    else:
        em = "fatal error: illegal instruction"
        print(em)
        CYCLES_PER_FRAME = 0
        if not debug_mode:
            input("press enter to exit")
            sys.exit(0)
    
    how_many_cycles_took_after = cpu_cycles
    cpu_cycles_took_for_opcode = how_many_cycles_took_after - how_many_cycles_took_before
    P = get_p()
    update_ppu_timers(cpu_cycles_took_for_opcode)
    return

# main:
def printlistdebugcmds():
    print("debug commands:")
    print("[ENTER KEY] - step CPU forward")
    print("s <steps: num> - run for <steps> CPU cycles")
    print("j <addr: uint16 (hex)> - jump PC to addr")
    print("f - step CPU forward entire single frame")
    print("e <count: num> - execute fixed amount of instructions (turbo)")
    print("r <addr: uint16 (hex)> - read that addr")
    print("w <addr: uint16 (hex)> <val: uint8 (hex)> - overwrite that addr with val")
    print("rr <row addr: uint12 (hex)> - read that entire addr row")
    print("CTRL+C+ENTER - exit")

def tryint(string):
    try:
        return int(string)
    except:
        return None

def tryhex(string):
    try:
        return int(string, 16)
    except:
        return None

def step_forward(steps=1):
    for _ in range(steps):
        step_cpu()

def step_forward_until_frame():
    global frame_rendered_this_step
    frame_rendered_this_step = False
    
    while not frame_rendered_this_step:
        step_cpu()

def init_nondebug():
    global CYCLES_PER_FRAME, FPS, instruction_count
    clock = pygame.time.Clock()
    
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)
        
        start_t = time.perf_counter()
        instr_before = instruction_count
        
        step_forward(CYCLES_PER_FRAME)
        
        end_t = time.perf_counter()
        instr_after = instruction_count
        
        executed_this_frame = instr_after - instr_before
        duration = end_t - start_t
        
        print(f"executed {executed_this_frame} CPU instructions in {duration:.4f} seconds.")
        
        clock.tick(FPS)

def init_debug():
    # idea: debug commands
    global PC, CYCLES_PER_FRAME
    saved_CPF = CYCLES_PER_FRAME
    printlistdebugcmds()
    print()
    while debugrunning:
        debugcmd = input()
        parts = debugcmd.split(); bcmd = ''; args = [];
        if not parts == []:
            bcmd = parts[0]
            args = parts[1:]
        
        sys.stdout.write("\033[F\033[K")
        sys.stdout.flush()
        
        if bcmd == '' and args == []:
            step_cpu()
        elif bcmd == 's':
            if len(args) >= 1:
                if not tryint(args[0]) == None:
                    steps = int(args[0])
                    step_forward(steps)
                else:
                    print('cmd err: arg <steps> is not a number')
            else:
                print('arg(s) missing: <steps>')
        elif bcmd == 'j':
            if len(args) >= 1:
                if tryhex(args[0]) is not None:
                    addr = tryhex(args[0])
                    if addr < 0x10000:
                        PC = addr
                        print(f'jumped to ${PC:04X}')
                    else:
                        print('cmd err: arg <addr> extended beyond uint16 limit')
                else:
                    print('cmd err: arg <addr> is not a hex number')
            else:
                print('arg(s) missing: <addr: uint16 (hex)>')
        elif bcmd == 'f':
            step_forward(saved_CPF)
        elif bcmd == 'e':
            if len(args) >= 1 and tryint(args[0]) is not None:
                limit = int(args[0])
                for _ in range(limit):
                    step_cpu()
            else:
                print('arg(s) missing or invalid: <count>')
        elif bcmd == 'r':
            if len(args) >= 1 and tryhex(args[0]) is not None:
                addr = tryhex(args[0])
                if addr < 0x10000:
                    out = cpu_read(addr)
                    print(f'${addr:04X}: ${out:02X}')
                else:
                    print('cmd err: arg <addr> extended beyond uint16 limit')
            else:
                print('arg(s) missing or invalid: <addr: uint16> (hex)')
        elif bcmd == 'w':
            if len(args) >= 2 and tryhex(args[0]) is not None and tryhex(args[1]) is not None:
                addr = tryhex(args[0])
                val = tryhex(args[1])
                if val < 0x100:
                    if addr < 0x10000:
                        out = cpu_write(addr, val)
                        print(f'${addr:04X}: ${out:02X}')
                    else:
                        print('cmd err: arg <addr> extended beyond uint16 limit')
                else:
                    print('cmd err: arg <val> extended beyond uint8 limit')
            else:
                print('arg(s) missing or invalid: <addr: uint16 (hex)> <val: uint8 (hex)>')
        elif bcmd == 'rr':
            if len(args) >= 1 and tryhex(args[0]) is not None:
                row = tryhex(args[0])
                if row < 0x1000:
                    row <<= 4
                    out = [0] * 16
                    outstr = ""
                    for i in range(len(out)):
                        out[i] = cpu_read(row+i)
                        outstr += f" ${out[i]:02X}"
                    print(f'${row:04X}:{outstr}')
                else:
                    print('cmd err: arg <addr> extended beyond uint12 limit')
            else:
                print('arg(s) missing or invalid: <row addr: uint12> (hex)')
        else:
            print('invalid debug cmd')

def init():
    global cpu_cycles, PC, instructions, frame_start_time
    load_rom()
    pre_decode_chr()
    
    if debug_mode:
        print("debugmode is on!")
        print(f"debug info: there are {len(instructions)} opcodes.")
        frame_start_time = time.perf_counter()
        init_debug()
    else:
        init_nondebug()

try:
    init()
except KeyboardInterrupt:
    input("\npress enter to exit")
#except Exception as em:
    #print(f"\nAN ERROR HAS OCCURED!\nPYTHON:\n{em}")
    #input("\npress enter to exit")
