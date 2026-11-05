"""QR codes in pure Python (2.12), for the inventory label of a PC: byte mode, error correction level M, versions 1-10
(up to 213 bytes), the mask with the lowest penalty. Follows ISO/IEC 18004; the tests compare it with a reference
encoder when one is installed. svg() draws it with a quiet zone of 4 modules."""
from __future__ import annotations

from typing import List, Optional

ECC_PER_BLOCK = [0, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26]  # level M, by version
BLOCKS = [0, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5]
MAX_VERSION = 10


def _raw_modules(ver: int) -> int:
    n = (16 * ver + 128) * ver + 64
    if ver >= 2:
        allinea = ver // 7 + 2
        n -= (25 * allinea - 10) * allinea - 55
        if ver >= 7:
            n -= 36
    return n


def _data_codewords(ver: int) -> int:
    return _raw_modules(ver) // 8 - ECC_PER_BLOCK[ver] * BLOCKS[ver]


def _gf_mul(x: int, y: int) -> int:
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _divisor(grado: int) -> List[int]:
    r = [0] * (grado - 1) + [1]
    radice = 1
    for _ in range(grado):
        for j in range(grado):
            r[j] = _gf_mul(r[j], radice)
            if j + 1 < grado:
                r[j] ^= r[j + 1]
        radice = _gf_mul(radice, 0x02)
    return r


def _remainder(dati: List[int], divisore: List[int]) -> List[int]:
    r = [0] * len(divisore)
    for b in dati:
        f = b ^ r.pop(0)
        r.append(0)
        for i, c in enumerate(divisore):
            r[i] ^= _gf_mul(c, f)
    return r


def _bit(x: int, i: int) -> bool:
    return (x >> i) & 1 != 0


class QR:
    def __init__(self, dati: bytes, version: Optional[int] = None, mask: Optional[int] = None):
        if version is None:
            version = next((v for v in range(1, MAX_VERSION + 1) if len(dati) <= _data_codewords(v) - (2 if v < 10 else 3)), 0)
            if not version:
                raise ValueError("Too much text for a QR code of this size.")
        self.version = version
        self.size = version * 4 + 17
        self.modules = [[False] * self.size for _ in range(self.size)]
        self.function = [[False] * self.size for _ in range(self.size)]
        self._function_patterns()
        self._codewords(self._interleave(self._encode(dati)))
        if mask is None:
            migliore, punti = 0, None
            for m in range(8):
                self._mask(m)
                self._format(m)
                p = self._penalty()
                if punti is None or p < punti:
                    migliore, punti = m, p
                self._mask(m)
            mask = migliore
        self.mask = mask
        self._mask(mask)
        self._format(mask)

    # ---------- layout ----------
    def _set(self, x: int, y: int, scuro: bool) -> None:
        self.modules[y][x] = scuro
        self.function[y][x] = True

    def _alignment(self) -> List[int]:
        if self.version == 1:
            return []
        n = self.version // 7 + 2
        passo = (self.version * 8 + n * 3 + 5) // (n * 4 - 4) * 2
        return list(reversed([self.size - 7 - i * passo for i in range(n - 1)] + [6]))

    def _function_patterns(self) -> None:
        for i in range(self.size):
            self._set(6, i, i % 2 == 0)
            self._set(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (self.size - 4, 3), (3, self.size - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < self.size and 0 <= y < self.size:
                        self._set(x, y, max(abs(dx), abs(dy)) not in (2, 4))
        pos = self._alignment()
        ultimo = len(pos) - 1
        for i, a in enumerate(pos):
            for j, b in enumerate(pos):
                if (i, j) in ((0, 0), (0, ultimo), (ultimo, 0)):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self._set(a + dx, b + dy, max(abs(dx), abs(dy)) != 1)
        self._format(0)
        if self.version >= 7:
            r = self.version
            for _ in range(12):
                r = (r << 1) ^ ((r >> 11) * 0x1F25)
            bits = self.version << 12 | r
            for i in range(18):
                a, b = self.size - 11 + i % 3, i // 3
                self._set(a, b, _bit(bits, i))
                self._set(b, a, _bit(bits, i))

    def _format(self, mask: int) -> None:
        dati = 0 << 3 | mask  # level M = 0
        r = dati
        for _ in range(10):
            r = (r << 1) ^ ((r >> 9) * 0x537)
        bits = (dati << 10 | r) ^ 0x5412
        for i in range(6):
            self._set(8, i, _bit(bits, i))
        self._set(8, 7, _bit(bits, 6))
        self._set(8, 8, _bit(bits, 7))
        self._set(7, 8, _bit(bits, 8))
        for i in range(9, 15):
            self._set(14 - i, 8, _bit(bits, i))
        for i in range(8):
            self._set(self.size - 1 - i, 8, _bit(bits, i))
        for i in range(8, 15):
            self._set(8, self.size - 15 + i, _bit(bits, i))
        self._set(8, self.size - 8, True)

    # ---------- data ----------
    def _encode(self, dati: bytes) -> List[int]:
        bits: List[int] = []

        def add(valore: int, n: int) -> None:
            bits.extend((valore >> i) & 1 for i in reversed(range(n)))
        add(0b0100, 4)
        add(len(dati), 8 if self.version < 10 else 16)
        for b in dati:
            add(b, 8)
        capacita = _data_codewords(self.version) * 8
        add(0, min(4, capacita - len(bits)))
        add(0, -len(bits) % 8)
        pad = 0xEC
        while len(bits) < capacita:
            add(pad, 8)
            pad ^= 0xEC ^ 0x11
        return [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]

    def _interleave(self, dati: List[int]) -> List[int]:
        n, ecc = BLOCKS[self.version], ECC_PER_BLOCK[self.version]
        grezzi = _raw_modules(self.version) // 8
        corti = n - grezzi % n
        lung = grezzi // n
        div = _divisor(ecc)
        blocchi, k = [], 0
        for i in range(n):
            d = dati[k:k + lung - ecc + (0 if i < corti else 1)]
            k += len(d)
            e = _remainder(d, div)
            if i < corti:
                d = d + [0]
            blocchi.append(d + e)
        fuori = []
        for i in range(len(blocchi[0])):
            for j, b in enumerate(blocchi):
                if i != lung - ecc or j >= corti:
                    fuori.append(b[i])
        return fuori

    def _codewords(self, dati: List[int]) -> None:
        i = 0
        destra = self.size - 1
        while destra >= 1:
            if destra == 6:
                destra = 5
            for vert in range(self.size):
                for j in range(2):
                    x = destra - j
                    su = ((destra + 1) & 2) == 0
                    y = self.size - 1 - vert if su else vert
                    if not self.function[y][x] and i < len(dati) * 8:
                        self.modules[y][x] = _bit(dati[i >> 3], 7 - (i & 7))
                        i += 1
            destra -= 2

    def _mask(self, m: int) -> None:
        regole = [lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0, lambda x, y: (x + y) % 3 == 0,
                  lambda x, y: (x // 3 + y // 2) % 2 == 0, lambda x, y: x * y % 2 + x * y % 3 == 0,
                  lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0, lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0]
        f = regole[m]
        for y in range(self.size):
            for x in range(self.size):
                if not self.function[y][x] and f(x, y):
                    self.modules[y][x] = not self.modules[y][x]

    def _penalty(self) -> int:
        n, p = self.size, 0
        righe = ["".join("1" if c else "0" for c in r) for r in self.modules]
        colonne = ["".join("1" if self.modules[y][x] else "0" for y in range(n)) for x in range(n)]
        for linea in righe + colonne:
            corsa, prec = 0, ""
            for ch in linea + "x":
                if ch == prec:
                    corsa += 1
                else:
                    if corsa >= 5:
                        p += 3 + corsa - 5
                    corsa, prec = 1, ch
            esteso = "0000" + linea + "0000"
            p += 40 * (esteso.count("10111010000") + esteso.count("00001011101"))
        for y in range(n - 1):
            for x in range(n - 1):
                c = self.modules[y][x]
                if c == self.modules[y][x + 1] == self.modules[y + 1][x] == self.modules[y + 1][x + 1]:
                    p += 3
        scuri = sum(sum(r) for r in self.modules)
        p += abs(scuri * 20 - n * n * 10) // (n * n) * 10
        return p


def svg(testo: str, modulo: int = 4) -> str:
    q = QR(testo.encode("utf-8"))
    lato = (q.size + 8) * modulo
    tratti = "".join(f"M{(x + 4) * modulo},{(y + 4) * modulo}h{modulo}v{modulo}h-{modulo}z"
                     for y in range(q.size) for x in range(q.size) if q.modules[y][x])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {lato} {lato}" width="{lato}" height="{lato}" shape-rendering="crispEdges">'
            f'<rect width="100%" height="100%" fill="#fff"/><path d="{tratti}" fill="#000"/></svg>')
