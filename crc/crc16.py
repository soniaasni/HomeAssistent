"""CRC-16/CCITT-FALSE über einen Speicherbereich, gegeben durch baseAddress und Size.

Python-Port der C-Funktion calcCrc16Bit() und ihre Anwendung auf einen
Speicherbereich. Herleitung, Annahmen und Validierung: README.md.

In C (auf dem 32-Bit-Zielsystem) ist die gesamte Lösung eine Zeile:

    uint16_t crc = calcCrc16Bit((uint16_t *)baseAddress, Size / 2);

Kommandozeile (Sollwert am PC aus einem Speicherabbild berechnen):

    python crc16.py firmware.bin 0x08004000 0x1000 --file-start 0x08000000
"""

import argparse

POLY = 0x1021  # Generatorpolynom x^16 + x^12 + x^5 + 1 (im C-Code: 4129)
INIT = 0xFFFF  # Startwert (im C-Code: 65535)


def calc_crc16_bit(words):
    """1:1-Port von calcCrc16Bit(): CRC über eine Folge von 16-Bit-Wörtern.

    Jedes Wort wird mit dem höchstwertigen Bit (Bit 15) zuerst verarbeitet.
    Die Hilfsvariable Syndrome des C-Codes ist hier crc selbst.
    """
    crc = INIT
    for word in words:
        for _ in range(16):
            if (word & 0x8000) ^ (crc & 0x8000):  # Bit 15 von Wort und CRC verschieden?
                crc = ((crc << 1) ^ POLY) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
            word = (word << 1) & 0xFFFF  # nächstes Bit des Worts an Position 15
    return crc


def calc_crc16_region(memory, base_address, size, byteorder="little"):
    """CRC über die `size` Bytes ab `base_address`.

    Entspricht in C:  calcCrc16Bit((uint16_t *)baseAddress, Size / 2)

    memory        Speicherabbild (bytes), memory[i] ist das Byte an Adresse i
    base_address  Startadresse, gerade (16-Bit-ausgerichtet)
    size          Länge in Bytes, gerade (ganze 16-Bit-Wörter)
    byteorder     wie das Zielsystem zwei Bytes zu einem Wort liest:
                  "little" (z. B. ARM Cortex-M, x86) oder "big"
    """
    if base_address % 2 or size % 2:
        raise ValueError("baseAddress und Size müssen gerade sein (16-Bit-Wörter)")
    if base_address < 0 or size < 0 or base_address + size > len(memory):
        raise ValueError("Bereich liegt nicht vollständig im Speicherabbild")
    words = (int.from_bytes(memory[a:a + 2], byteorder)
             for a in range(base_address, base_address + size, 2))
    return calc_crc16_bit(words)


def main():
    parser = argparse.ArgumentParser(
        description="CRC-16/CCITT-FALSE über einen Bereich eines Speicherabbilds.")
    parser.add_argument("file", help="Speicherabbild, z. B. firmware.bin")
    parser.add_argument("baseAddress", type=lambda s: int(s, 0),
                        help="Startadresse des Bereichs, z. B. 0x08004000")
    parser.add_argument("Size", type=lambda s: int(s, 0),
                        help="Länge des Bereichs in Bytes, z. B. 0x1000")
    parser.add_argument("--file-start", type=lambda s: int(s, 0), default=0,
                        help="Adresse des ersten Bytes der Datei (Standard: 0)")
    parser.add_argument("--big-endian", action="store_true",
                        help="Zielsystem ist Big-Endian (Standard: Little-Endian)")
    args = parser.parse_args()

    with open(args.file, "rb") as f:
        memory = f.read()
    try:
        crc = calc_crc16_region(memory, args.baseAddress - args.file_start, args.Size,
                                "big" if args.big_endian else "little")
    except ValueError as error:
        parser.error(str(error))
    print(f"0x{crc:04X}")


if __name__ == "__main__":
    main()
