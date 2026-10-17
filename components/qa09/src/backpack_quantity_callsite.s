.section .text
.global _start

# Far-call replacement at ROM 0x33835C: 7D6D:0008 resolves to the verified
# zero host span at ROM 0x37D6D8.
_start:
    .byte 0x9a, 0x08, 0x00, 0x6d, 0x7d
