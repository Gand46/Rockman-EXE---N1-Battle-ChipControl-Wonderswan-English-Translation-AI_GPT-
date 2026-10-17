.code16
.intel_syntax noprefix
.section .text
.global _start

# Graphics Advance 6 quantity renderer.
#
# The original caller passes five 16-bit arguments:
#   value, x, y, one_digit, palette
# This wrapper first calls the untouched numeric renderer so its tile-cache
# bookkeeping remains canonical.  It then reassigns only the quantity cell to
# one exclusive pair selected from the complete cross-layer free-set and draws
# a compact 3x5 superscript.
# The code is hosted at ROM
# 0x37D6D8 (physical 7D6D:0008); the region is verified zero before insertion.
_start:
    push bp
    mov bp, sp

    push word ptr ss:[bp+14]
    push word ptr ss:[bp+12]
    push word ptr ss:[bp+10]
    push word ptr ss:[bp+8]
    push word ptr ss:[bp+6]
    lcall 0x22ae, 0x0369
    add sp, 10

    # Preserve the exact register result of the original renderer.
    push ax
    push bx
    push cx
    push dx
    push ds
    push es
    push si
    push di

    # Locate the BG1 staging-map cell at C000.
    mov ax, word ptr ss:[bp+10]
    shl ax, 6
    mov bx, word ptr ss:[bp+8]
    shl bx, 1
    add bx, ax
    mov ax, 0x0c00
    mov es, ax

    # Assign one exclusive two-tile cell per visible list row.  The seven
    # pairs were proved unreferenced by every relevant ROM map and by both
    # complete live 32x32 maps across the project capture corpus.  They also
    # sit above the complete OBJ tile-ID range.  Map attributes are retained.
    mov ax, word ptr ss:[bp+10]
    sub ax, 3
    shr ax, 1
    shl ax, 1
    mov si, offset quantity_tiles + 8
    add si, ax
    mov di, word ptr cs:[si]
    mov ax, di
    mov dx, word ptr es:[bx]
    and dx, 0xfe00
    mov cx, dx
    or dx, ax
    mov word ptr es:[bx], dx
    inc ax
    or ax, cx
    mov word ptr es:[bx+0x40], ax

    # Convert the exclusive upper tile ID to its 4bpp VRAM address.
    mov ax, di
    shl ax, 5
    add ax, 0x4000
    mov di, ax

    # A palette argument of 1/2 corresponds to packed backgrounds 22/44.
    mov ax, word ptr ss:[bp+14]
    and ax, 0x000f
    mov bx, 0x2222
    mul bx

    # Clear the original full-height digit in both 8x8 tiles.
    mov cx, 32
    xor bx, bx
    mov es, bx
    cld
    rep stosw
    sub di, 60

    # Match the original one-column behaviour for unexpected values >= 10.
    mov ax, word ptr ss:[bp+6]
    xor dx, dx
    mov bx, 10
    div bx
    mov ax, dx
    mov bx, ax
    shl ax, 2
    add ax, bx
    mov si, offset digit_masks + 8
    add si, ax
    push cs
    pop ds

    # Restore the background addend and draw five rows at x=4..6, y=1..5.
    mov ax, word ptr ss:[bp+14]
    and ax, 0x000f
    mov bx, 0x2222
    mul bx
    mov dx, ax
    mov cx, 5

draw_row:
    lodsb
    xor ah, ah
    shl ax, 1
    mov bx, ax
    mov ax, word ptr cs:[row_masks+bx+8]
    add ax, dx
    mov word ptr es:[di+2], ax
    add di, 4
    loop draw_row

    pop di
    pop si
    pop es
    pop ds
    pop dx
    pop cx
    pop bx
    pop ax
    pop bp
    lret

# Each digit stores five three-bit row masks.  row_masks expands each mask to
# the packed 4bpp increments for x=4,5 and 6.  Adding the palette background
# turns zero nibbles into background and one nibbles into the original
# foreground colour, with no filtering or antialiasing.
digit_masks:
    # 0: 111 / 101 / 101 / 101 / 111
    .byte 7, 5, 5, 5, 7
    # 1: 010 / 110 / 010 / 010 / 111
    .byte 2, 6, 2, 2, 7
    # 2: 111 / 001 / 111 / 100 / 111
    .byte 7, 1, 7, 4, 7
    # 3: 111 / 001 / 111 / 001 / 111
    .byte 7, 1, 7, 1, 7
    # 4: 101 / 101 / 111 / 001 / 001
    .byte 5, 5, 7, 1, 1
    # 5: 111 / 100 / 111 / 001 / 111
    .byte 7, 4, 7, 1, 7
    # 6: 111 / 100 / 111 / 101 / 111
    .byte 7, 4, 7, 5, 7
    # 7: 111 / 001 / 010 / 010 / 010
    .byte 7, 1, 2, 2, 2
    # 8: 111 / 101 / 111 / 101 / 111
    .byte 7, 5, 7, 5, 7
    # 9: 111 / 101 / 111 / 001 / 111
    .byte 7, 5, 7, 1, 7

row_masks:
    .word 0x0000, 0x1000, 0x0001, 0x1001
    .word 0x0010, 0x1010, 0x0011, 0x1011

quantity_tiles:
    .word 0x00bc, 0x00be, 0x00c0, 0x00c6
    .word 0x00d6, 0x00e0, 0x00e2
