#!/usr/bin/env python3
"""
patch_game_assistant.py - przenosi patche z Game_Assistant_10_21_3_MOD_ na nowsze wersje (testowane na 10.42.5).

Uzycie:
  java -jar apktool.jar d -f -o dec Game_Assistant_XX.apk
  python3 patch_game_assistant.py dec            # patchuje
  python3 patch_game_assistant.py dec --dry-run  # tylko pokazuje co by zmienil
  python3 patch_game_assistant.py dec --extras   # + tryb GT, wibracje 4D, ping (--gt --4d --ping --caps --tile osobno; --tile = kafelek Stan systemu, niepewny)
  python3 patch_game_assistant.py dec --risky    # + mniej pewny patch (cache-check w GlobalFilter)
  java -jar apktool.jar b dec -o out_unsigned.apk

Metody sa szukane po STALYCH stringach logow w ciele metody (nazwy typu m0/G/t zmieniaja
sie miedzy buildami), a nie po nazwach. Jesli hint nie znajdzie dokladnie 1 metody,
patch jest pomijany i raportowany (zeby nie zepsuc zlej metody).
"""
import os, re, sys, glob

# (klasa, opis, sygnatura-regex, hint (string w ciele metody), wartosc, wymagane)
TARGETS = [
    # --- FrameInsertFeature (wstawka klatek / super frame)
    ("business/module/frameinsert/FrameInsertFeature", "isFeatureEnabled",
     r"isFeatureEnabled\(Ljava/lang/String;\)Z", None, 1, True),
    ("business/module/frameinsert/FrameInsertFeature", "isCloudSupport (stare nazwy: isCloudSupport)",
     r"\w+\(\)Z", "one_plus_characteristic", 1, True),
    ("business/module/frameinsert/FrameInsertFeature", "isSupportUniqueFrameInsert (stare: m0)",
     r"\w+\(\)Z", "isSupportUniqueFrameInsert: [result ", 1, True),
    ("business/module/frameinsert/FrameInsertFeature", "getSmartFrameSwitch (stare: G)",
     r"\w+\(Ljava/lang/String;\)Z", "getSmartFrameSwitch ,pkgName:", 1, True),
    ("business/module/frameinsert/FrameInsertFeature", "cloudFrameInsertEnable (stare: t)",
     r"\w+\(Ljava/lang/String;\)Z", "cloudFrameInsertEnable: ", 1, True),
    # --- GameGlobalFilterFeature (filtr globalny)
    ("business/module/gamefilter/global/GameGlobalFilterFeature", "isFeatureEnabled",
     r"isFeatureEnabled\(Ljava/lang/String;\)Z", None, 1, True),
    ("business/module/gamefilter/global/GameGlobalFilterFeature", "isGameColorSpaceBlackList (stare: F)",
     r"\w+\(Ljava/lang/String;\)Z", "isGameColorSpaceBlackList ,pkgName:", 0, True),
    ("business/module/gamefilter/global/GameGlobalFilterFeature", "isGameSceneBeautifyWhiteList (stare: H)",
     r"\w+\(Ljava/lang/String;\)Z", "isGameSceneBeautifyWhiteList ,pkgName:", 1, True),
    # --- blokada regionu konta ("Account unavailable ... country or region") - nowe w 10.42.x
    ("com/oplus/games/account/AccountFacade", "isInvalidAccountCountry wrapper (C)",
     r"\w+\(J\)Z", "isInvalidAccountCountry", 0, True),
    ("com/oplus/games/feature/account/AccountCheckManager", "Invalid_account_country check (e)",
     r"\w+\(Lcom/oplus/games/arch/core/\w+;\)Z", "Invalid_account_country", 0, True),
    ("com/oplus/games/feature/account/AccountCheckManager", "dialog 'Account unavailable' (i) -> return-void",
     r"\w+\(\)V", "showEuropeAccountDialog$1;->INSTANCE", "void", True),
    # --- mniej pewne (dopasowanie po kontekscie wywolan, nie po stringu) - opcjonalne
    ("business/module/gamefilter/global/GameGlobalFilterFeature", "cache-check (stare: s) - OPCJONALNE",
     r"D\(Ljava/lang/String;\)Z", "Ljava/util/concurrent/ConcurrentHashMap;->get", 1, False),
]

# --- OPCJONALNE GRUPY (flagi: --gt --4d --tile --ping --caps --feat --export  albo --extras = wszystkie poza tile, feat i export)
# (klasa, opis, sygnatura, hint, wartosc, wymagane, grupa, multi)
EXTRA_TARGETS = [
    # Tryb GT: flaga oplus.software.support.gt.mode czytana przez OplusFeatureHelper
    ("com/oplus/addon/OplusFeatureHelper", "isSupportGtMode (GT mode)",
     r"\w+\(\)Z", "isSupportGtMode hasFeature = ", 1, True, "gt", False),
    # Wibracje 4D: helper GameFourDVibrationSupportUtil (com/coloros/gamespaceui/utils/s)
    ("com/coloros/gamespaceui/utils/s", "4D cloud support (c)",
     r"\w+\(\)Z", "isFourDVibrationGameCloudSupport(), support: ", 1, True, "4d", False),
    ("com/coloros/gamespaceui/utils/s", "4D haptic feature checks (b, f)",
     r"\w+\(\)Z", "Lcom/oplus/addon/OplusFeatureHelper;->", 1, True, "4d", True),
    # Kafelek "Stan systemu" (FPS, CPU, GPU...)
    ("business/gamedock/tiles/i1", "tile isApplicable (Stan systemu)",
     r"isApplicable\(\)Z", "feature_sys_usage", 1, True, "tile", False),
]
# --caps: flagi mozliwosci ekranu/obrazu (jak w modzie 10.9.6: FeatureFlag.* zwraca "1")
_FF = "com/oplus/addon/FeatureFlag"
_S = r"\w+\(Ljava/lang/String;\)Ljava/lang/String;"
CAPS_TARGETS = [
    (_FF, "OSR 1.0 super resolution", _S, "isSupportGameOSR10SuperResolution, pkgName:", "S1", True, "caps", False),
    (_FF, "OSR 2.0 super resolution", _S, "isSupportGameOSR20SuperResolution, pkgName:", "S1", True, "caps", False),
    (_FF, "DSR super resolution", _S, "isSupportGameDSRSuperResolution, pkgName:", "S1", True, "caps", False),
    (_FF, "super resolution (SR)", _S, "isSuperResolution, pkgName:", "S1", True, "caps", False),
    (_FF, "SDR->HDR", _S, "isSupportSdr2hdr, pkgName:", "S1", True, "caps", False),
    (_FF, "EDR", _S, "isSupportEDR, pkgName:", "S1", True, "caps", False),
    (_FF, "EDR3", _S, "isSupportEDR3, pkgName:", "S1", True, "caps", False),
    (_FF, "ultra high quality (DAPR)", _S, "isSupportUltraHighQuality, pkgName:", "S1", True, "caps", False),
    (_FF, "image quality / frame rate first", _S, "isSupportImageQualityAndFrameRateFirst, pkgName:", "S1", True, "caps", False),
    (_FF, "game AI tool", _S, "isSupportGameAiTool, pkgName:", "S1", True, "caps", False),
    (_FF, "other frame insert (MEMC)", _S, "isSupportOtherFrameInsert, pkgName  is null", "S1", True, "caps", False),
    (_FF, "frame insert (iMEMC)", _S, "isSupportFrameInsert, pkgName:", "S1", True, "caps", False),
    (_FF, "frame insert MFRC", _S, "isSupportFrameInsertMFRC, pkgName:", "S1", True, "caps", False),
    ("business/module/touchopt/TouchControlFeature", "touch control isFeatureEnabled",
     r"isFeatureEnabled\(Ljava/lang/String;\)Z", None, 1, True, "caps", False),
]


# --feat: flagi funkcji w OplusFeatureHelper (hasFeature) - wymuszenie "true". Szukane po stringu logu w ciele metody.
# Tylko funkcje programowe (obraz/kolor/klatki/SR); bez sprzetowych (wentylator, triggery, joystick, silnik wibracji).
_OFH = "com/oplus/addon/OplusFeatureHelper"
_B = r"\w+\(\)Z"
FEAT_TARGETS = [(_OFH, label, _B, hint, 1, True, "feat", False) for label, hint in [
    ("frame insert (memc_enable)", "isSupportFrameInsert hasFeature = "),
    ("frame insert 144 (extreme_insert)", "isSupportFrameInsert144 hasFeature = "),
    ("frame insert MFRC", "isSupportFrameInsertMFRC = "),
    ("frame insert OFRC", "isSupportFrameInsertOfrc = "),
    ("unique frame insert (fps limit mode)", "isSupportUniqueFrameInsert hasFeature = "),
    ("increase fps (memc)", "isSupportIncreaseFps hasFeature = "),
    ("super frame UI 3.0", "isSupportSuperFrameUI3_0 = "),
    ("game color mode 1.0", "isSupportGameColorMode1 = "),
    ("game color mode 2.0", "isSupportGameColorMode2 = "),
    ("game color space", "isSupportGameColorSpace = "),
    ("game filter 2.0", "isSupportGameFilter2 = "),
    ("game HQV plus", "isSupportGameHqvPlus hasFeature = "),
    ("game HQV EDR (HDR 2.0)", "isSupportGameHqvEDR hasFeature = "),
    ("game eye care", "isSupportGameEyeCare "),
    ("DSR", "isSupportDSR "),
    ("AI SR", "isSupportGameAISR = "),
    ("full super resolution", "isSupportFullSupperResolution = "),
    ("super resolution UPS", "isSupportSuperResolutionUps "),
]]

# kafelki w panelu (Tools) zalezne od metod Feature: filtr gry i ochrona oczu
FEAT_TARGETS += [
    ("business/module/gamefilter/GameFilterFeature", "kafelek Filtr gry (isGameFilterEntrySupported)",
     r"isGameFilterEntrySupported\(\)Z", None, 1, True, "feat", False),
    ("business/module/gamefilter/GameFilterFeature", "Filtr gry isFeatureEnabled",
     r"isFeatureEnabled\(Ljava/lang/String;\)Z", None, 1, True, "feat", False),
    ("business/module/gameeyecare/GameEyeCareFeature", "kafelek Ochrona oczu (isFeatureEnabled)",
     r"isFeatureEnabled\(Ljava/lang/String;\)Z", None, 1, True, "feat", False),
]

# --export: flaga "export" (com/oplus/a._isExport) czytana przez k(). false = apka zachowuje sie jak wersja krajowa:
# odblokowuje m.in. wlasne wibracje, popup kart, animacje ekranu, adapter Vulkan, SR z warunkiem isExport.
# Uwaga: wplywa tez na rzeczy zalezne od regionu (uslugi/tresci CN) - dlatego osobny, jawny przelacznik.
EXPORT_TARGETS = [
    ("com/oplus/a", "isExport -> false (k)", r"\w+\(\)Z", "Please init Environment _isExport", 0, True, "export", False),
]

TILE_MARK = "isExportFlavor: add SysUsageTile"

# --ping: pomiar opoznienia ("Network xx ms") domyslnie szedl do Baidu (chinskie serwery).
# (fragment sciezki pliku, stary string, nowy string)
PING_REPLACEMENTS = [
    ("po0/", '"ping -c 1 39.156.66.18"', '"ping -c 1 8.8.8.8"'),       # twardy IP Baidu -> Google DNS
    ("po0/g$d", '"www.baidu.com"', '"www.google.com"'),               # domyslny host
    ("po0/g.smali", '"PING www.baidu.com"', '"PING www.google.com"'),  # parser naglowka ping musi pasowac do hosta
    ("gameboard/datamanager/GameBoardHelp", '"https://www.baidu.com/"', '"https://www.google.com/"'),
]

CLASS_ALIAS = {}

def find_smali(rel):
    return glob.glob(os.path.join(sys.argv[1], "smali*", rel + ".smali"))

METHOD_RE = re.compile(r"(\.method [^\n]*\n)(.*?)(\n\.end method)", re.S)

def split_header_body(body):
    """Zwraca (header, reszta). Header = .locals/.param/.annotation (zachowujemy)."""
    lines = body.split("\n")
    hdr, i, in_block = [], 0, None
    while i < len(lines):
        s = lines[i].strip()
        if in_block:
            hdr.append(lines[i])
            if s == ".end " + in_block:
                in_block = None
        elif s.startswith(".annotation"):
            in_block = "annotation"; hdr.append(lines[i])
        elif s.startswith(".param"):
            hdr.append(lines[i])
            # .param moze byc jednolinijkowy albo z blokiem
            nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if nxt.startswith(".annotation") or any(
                    l.strip() == ".end param" for l in lines[i + 1:i + 6]):
                in_block = "param"
        elif s.startswith((".locals", ".registers")) or s == "":
            hdr.append(lines[i])
        else:
            break
        i += 1
    return "\n".join(hdr), "\n".join(lines[i:])

def make_body(header, value):
    if re.search(r"\.registers\b", header):
        pass  # zostawiamy
    elif not re.search(r"\.locals\s+[1-9]", header):
        header = re.sub(r"\.locals\s+\d+", ".locals 1", header) \
            if ".locals" in header else header + "\n    .locals 1"
    if value == "S1":
        if not re.search(r"\.locals\s+[1-9]", header):
            header = re.sub(r"\.locals\s+\d+", ".locals 1", header)
        return header.rstrip("\n") + '\n\n    const-string v0, "1"\n\n    return-object v0'
    if value == "void":
        return header.rstrip("\n") + "\n\n    return-void"
    return header.rstrip("\n") + "\n\n    const/4 v0, 0x%d\n\n    return v0" % value

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    dry = "--dry-run" in sys.argv
    ok = fail = 0
    risky = "--risky" in sys.argv
    groups = {g for g in ("gt", "4d", "tile", "ping", "caps", "feat", "export") if ("--" + g) in sys.argv or ("--extras" in sys.argv and g not in ("tile", "feat", "export"))}
    todo = [t + ("base", False) for t in TARGETS] + [t for t in (EXTRA_TARGETS + CAPS_TARGETS + FEAT_TARGETS + EXPORT_TARGETS) if t[6] in groups]
    for cls, label, sig, hint, val, required, _grp, multi in todo:
        if not required and not risky:
            print("[OPCJA] %-60s pominiete (uzyj --risky)" % label); continue
        files = find_smali(cls)
        if not files and cls in CLASS_ALIAS:
            files = [CLASS_ALIAS[cls]]
        if not files and hint and len(hint) > 25:
            # klasa zmienila nazwe/pakiet miedzy wersjami - szukamy pliku po stringu z hintu
            for _p in glob.glob(os.path.join(sys.argv[1], "smali*", "**", "*.smali"), recursive=True):
                try:
                    if hint in open(_p, encoding="utf-8", errors="ignore").read():
                        files = [_p]; CLASS_ALIAS[cls] = _p; break
                except OSError:
                    pass
        if not files:
            print("[BRAK ] %-60s klasa nie istnieje" % label); fail += required; continue
        path = files[0]
        text = open(path, encoding="utf-8").read()
        cands = []
        for m in METHOD_RE.finditer(text):
            head, body = m.group(1), m.group(2)
            if "abstract" in head or "native" in head or "synthetic" in head or "bridge" in head:
                continue
            if not re.search(r"\s" + sig + r"\s*$", head.strip()):
                continue
            if hint and hint not in body:
                continue
            cands.append(m)
        if hint is None:
            # bez hintu: dokladna nazwa+sygnatura, musi byc 1 dopasowanie
            pass
        if multi:   # tylko krotkie metody (<=4 instrukcji) - gettery feature
            cands = [c for c in cands if len([l for l in c.group(2).split("\n")
                     if l.strip() and not l.strip().startswith((".", "#", ":"))]) <= 4]
        if (not multi and len(cands) != 1) or (multi and not cands):
            print("[SKIP ] %-60s dopasowan: %d (%s)" % (label, len(cands), os.path.relpath(path, sys.argv[1])))
            fail += required; continue
        for m in reversed(cands):
            hdr, _rest = split_header_body(m.group(2))
            new = m.group(1) + make_body(hdr, val) + m.group(3)
            name = m.group(1).split("(")[0].split()[-1]
            print("[PATCH] %-60s %s -> %s  (%s)" % (
                label, name, ("return-void" if val == "void" else ("\"1\"" if val == "S1" else ("true" if val else "false"))), os.path.relpath(path, sys.argv[1])))
            if not dry:
                text = text[:m.start()] + new + text[m.end():]
        if not dry:
            open(path, "w", encoding="utf-8").write(text)
        ok += 1
    if "ping" in groups:
        for frag, old, new in PING_REPLACEMENTS:
            hit = 0
            for p in glob.glob(os.path.join(sys.argv[1], "smali*", "**", "*.smali"), recursive=True):
                if frag not in p.replace("\\", "/"):
                    continue
                t = open(p, encoding="utf-8", errors="ignore").read()
                if old in t:
                    hit += t.count(old)
                    print("[PATCH] ping: %s -> %s  (%s)" % (old, new, os.path.relpath(p, sys.argv[1])))
                    if not dry:
                        open(p, "w", encoding="utf-8").write(t.replace(old, new))
            if hit == 0:
                print("[SKIP ] ping: %s nie znaleziono" % old); fail += 1
            else:
                ok += 1
    if "tile" in groups:
        done = False
        for p in glob.glob(os.path.join(sys.argv[1], "smali*", "**", "*.smali"), recursive=True):
            t = open(p, encoding="utf-8", errors="ignore").read()
            if TILE_MARK not in t:
                continue
            i = t.index(TILE_MARK)
            head = t[max(0, i - 900):i]
            m = list(re.finditer(r"invoke-virtual \{(v\d+)\}, Lcom/oplus/\w+;->\w+\(\)Z(?:\s|\.line \d+)+move-result \1(?:\s|\.line \d+)+if-eqz \1, :\w+", head))
            if not m:
                continue
            m = m[-1]
            a = max(0, i - 900) + m.start(); b = max(0, i - 900) + m.end()
            print("[PATCH] %-60s dodawanie kafelka bez warunku export (%s)" % (
                "TilesManager: SysUsageTile", os.path.relpath(p, sys.argv[1])))
            if not dry:
                t = t[:a] + "const/4 %s, 0x1" % m.group(1) + t[b:]
                open(p, "w", encoding="utf-8").write(t)
            ok += 1; done = True
            break
        if not done:
            print("[SKIP ] TilesManager: SysUsageTile - nie znaleziono"); fail += 1
    print("\nGotowe: %d spatchowane, %d pominiete/blad" % (ok, fail))
    sys.exit(0 if fail == 0 else 2)

if __name__ == "__main__":
    main()
