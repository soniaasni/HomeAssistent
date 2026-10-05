"""Validierung von crc16.py – Methodik und Ergebnisse: README.md, Abschnitt 6.

Ausführen (aus dem Repository-Wurzelverzeichnis, nur Standardbibliothek):

    python -m unittest discover -s crc -v
"""

import binascii
import os
import random
import subprocess
import sys
import tempfile
import unittest

from crc16 import POLY, calc_crc16_bit, calc_crc16_region

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crc16.py")


def reference_crc(data):
    """Unabhängige Referenz: tabellengesteuerte CRC aus der Standardbibliothek."""
    return binascii.crc_hqx(data, 0xFFFF)


def swap_pairs(data):
    """Vertauscht je zwei benachbarte Bytes: b0 b1 b2 b3 ... -> b1 b0 b3 b2 ..."""
    swapped = bytearray(data)
    swapped[0::2], swapped[1::2] = data[1::2], data[0::2]
    return bytes(swapped)


class TestCrc16(unittest.TestCase):

    def test_v1_reference_is_crc16_ccitt_false(self):
        # Prüfwert des Verfahrens laut CRC-Katalog: "123456789" -> 0x29B1
        self.assertEqual(reference_crc(b"123456789"), 0x29B1)

    def test_v2_equals_reference_for_random_regions(self):
        rng = random.Random(1)  # fester Startwert -> reproduzierbar
        for _ in range(500):
            data = bytes(rng.randrange(256) for _ in range(2 * rng.randrange(65)))
            with self.subTest(data=data.hex()):
                # Big-Endian: Wort = Byte a (oben), Byte a+1 (unten) -> Bytes in Speicherreihenfolge
                self.assertEqual(calc_crc16_region(data, 0, len(data), "big"),
                                 reference_crc(data))
                # Little-Endian: Wort = Byte a+1 (oben), Byte a (unten) -> paarweise vertauscht
                self.assertEqual(calc_crc16_region(data, 0, len(data), "little"),
                                 reference_crc(swap_pairs(data)))

    def test_v2_equals_polynomial_definition(self):
        # Geschlossene Form, README Abschnitt 2.2: CRC(x) = (x^n * I(x) + x^16 * M(x)) mod G(x)
        def poly_mod(a, generator=0x10000 | POLY):
            while a.bit_length() > 16:
                a ^= generator << (a.bit_length() - 17)
            return a

        rng = random.Random(3)
        for _ in range(200):
            words = [rng.randrange(0x10000) for _ in range(rng.randrange(20))]
            n = 16 * len(words)  # Anzahl Datenbits
            message = int.from_bytes(b"".join(w.to_bytes(2, "big") for w in words), "big")
            with self.subTest(words=words):
                self.assertEqual(calc_crc16_bit(words),
                                 poly_mod((0xFFFF << n) ^ (message << 16)))

    def test_v3_vectors(self):
        cases = [  # (Speicherinhalt, CRC Little-Endian, CRC Big-Endian), README Abschnitt 4
            (b"", 0xFFFF, 0xFFFF),
            (bytes(4), 0x84C0, 0x84C0),
            (b"12345678", 0x3D14, 0xA12B),
        ]
        for data, little, big in cases:
            with self.subTest(data=data):
                self.assertEqual(calc_crc16_region(data, 0, len(data), "little"), little)
                self.assertEqual(calc_crc16_region(data, 0, len(data), "big"), big)
        # Standard ist Little-Endian (ARM Cortex-M, x86)
        self.assertEqual(calc_crc16_region(b"12345678", 0, 8), 0x3D14)
        # Wortebene, unabhängig von der Byte-Reihenfolge (Gegenprobe auf dem Zielsystem)
        self.assertEqual(calc_crc16_bit([0x3132, 0x3334, 0x3536, 0x3738]), 0xA12B)
        # Alternative Lesart, README Abschnitt 8: baseAddress = 0x08004000, Size = 0x1000
        self.assertEqual(calc_crc16_bit([0x0800, 0x4000, 0x0000, 0x1000]), 0x4687)

    def test_v4_only_the_region_counts(self):
        memory = bytes(range(256))
        self.assertEqual(calc_crc16_region(memory, 0x40, 0x20),
                         calc_crc16_region(memory[0x40:0x60], 0, 0x20))

    def test_v4_invalid_region_is_rejected(self):
        memory = bytes(16)
        for base, size in [(0, 3), (1, 2), (0, 18), (16, 2), (-2, 2)]:
            with self.subTest(base=base, size=size), self.assertRaises(ValueError):
                calc_crc16_region(memory, base, size)

    def test_v5_error_detection_limits(self):
        generator = 0x10000 | POLY  # G(x) einschließlich x^16

        # (a) Gerade Anzahl Terme <=> (x + 1) teilt G(x):
        #     jede ungerade Anzahl gekippter Bits wird erkannt
        self.assertEqual(bin(generator).count("1") % 2, 0)

        # (b) Ordnung von x modulo G(x): kleinstes d mit x^d mod G(x) = 1.
        #     Ein 2-Bit-Fehler x^i * (x^d + 1) bleibt genau dann unerkannt,
        #     wenn d ein Vielfaches davon ist.
        remainder, d = 1, 0
        while d == 0 or remainder != 1:
            remainder <<= 1
            if remainder & 0x10000:
                remainder ^= generator
            d += 1
        self.assertEqual(d, 32767)  # = 2^15 - 1

        # (c) Mit der echten Funktion: In 4 KiB (2048 Wörter = 32768 Bit) bleibt
        #     ein 2-Bit-Fehler im Abstand 32767 unerkannt -> HD = 2 ab 4 KiB
        rng = random.Random(2)
        words = [rng.randrange(0x10000) for _ in range(2048)]
        corrupted = list(words)
        corrupted[0] ^= 0x8000   # Datenbit 0 (zuerst verarbeitet)
        corrupted[-1] ^= 0x0001  # Datenbit 32767 (zuletzt verarbeitet)
        self.assertEqual(calc_crc16_bit(corrupted), calc_crc16_bit(words))

    def test_v6_command_line(self):
        image = bytes(4) + b"12345678"  # Datei beginnt an Adresse 0x08000000
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "image.bin")
            with open(path, "wb") as f:
                f.write(image)
            for extra, expected in [([], "0x3D14"), (["--big-endian"], "0xA12B")]:
                result = subprocess.run(
                    [sys.executable, SCRIPT, path, "0x08000004", "8",
                     "--file-start", "0x08000000"] + extra,
                    capture_output=True, text=True, check=True)
                self.assertEqual(result.stdout.strip(), expected)


if __name__ == "__main__":
    unittest.main()
