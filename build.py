"""Build Leraw from the sources in sources/.

Compiles each .glyphs file to a variable font with fontmake, then writes the static
instances and the WOFF2 web fonts:

    fonts/variable/Leraw[wght].ttf, Leraw-Italic[wght].ttf (+ .woff2)
    fonts/static/Leraw-Light.ttf ... Leraw-BlackItalic.ttf
"""
import os
import re
import subprocess
import sys
from datetime import datetime

from fontTools.otlLib.builder import buildStatTable
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables import ttProgram
from fontTools.varLib import instancer

FAMILY = 'Leraw'
ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, 'sources')
OUT = os.path.join(ROOT, 'fonts')
WEIGHTS = [(300, 'Light'), (400, 'Regular'), (500, 'Medium'), (600, 'SemiBold'),
           (700, 'Bold'), (800, 'ExtraBold'), (900, 'Black')]


def pin_timestamps(source):
    """Same sources, same bytes: date the fonts from the source instead of the build time."""
    if 'SOURCE_DATE_EPOCH' not in os.environ:
        text = open(source, encoding='utf-8').read()
        date = re.search(r'^date = "(.+)";$', text, re.M).group(1)
        stamp = datetime.strptime(date, '%Y-%m-%d %H:%M:%S %z').timestamp()
        os.environ['SOURCE_DATE_EPOCH'] = str(int(stamp))


def set_version(f):
    """LERAW_VERSION=1.1 (set from the git tag in CI) overrides the source's version as 1.100."""
    v = os.environ.get('LERAW_VERSION')
    if not v:
        return
    v = '%.3f' % float(v)
    old = 'Version %.3f' % f['head'].fontRevision
    f['head'].fontRevision = float(v)
    for rec in f['name'].names:
        if rec.nameID in (3, 5):
            s = rec.toUnicode()
            rec.string = s.replace(old, 'Version ' + v) if rec.nameID == 5 else s.replace(old[8:], v, 1)


def unhinted(f):
    """Smooth rendering for unhinted TrueType: gasp for all sizes, dropout control in prep."""
    gasp = newTable('gasp')
    gasp.gaspRange = {0xFFFF: 0x000F}
    f['gasp'] = gasp
    prep = newTable('prep')
    prep.program = ttProgram.Program()
    prep.program.fromAssembly(['PUSHW[]', '511', 'SCANCTRL[]', 'PUSHB[]', '4', 'SCANTYPE[]'])
    f['prep'] = prep


def stat(f, italic):
    """Weight names without the style, plus a Roman/Italic axis, so apps can combine them."""
    weights = [dict(value=w, name=n, **(dict(flags=2, linkedValue=700) if w == 400 else {})) for w, n in WEIGHTS]
    ital = dict(value=1, name='Italic') if italic else dict(value=0, name='Roman', flags=2, linkedValue=1)
    buildStatTable(f, [dict(tag='wght', name='Weight', values=weights),
                       dict(tag='ital', name='Italic', values=[ital])], elidedFallbackName='Regular')


def set_vertical_metrics(f):
    """Google Fonts vertical metrics schema:
    sTypoAscender = 950, sTypoDescender = -250, sTypoLineGap = 0
    hhea.ascent = 950, hhea.descent = -250, hhea.lineGap = 0
    Sum = 950 + abs(-250) + 0 = 1200 (120% of 1000 UPM)
    """
    f['hhea'].ascent = 950
    f['hhea'].descent = -250
    f['hhea'].lineGap = 0
    f['OS/2'].sTypoAscender = 950
    f['OS/2'].sTypoDescender = -250
    f['OS/2'].sTypoLineGap = 0


def fix_arabic_shaping(f):
    """Ensure Alef Maksura (uni0649) has initial and medial substitutions (mapping to Yeh init/medi)
    as required by Arabic shaping standards and Shaperglot.
    """
    if 'GSUB' not in f:
        return
    gsub = f['GSUB'].table
    feature_lookups = {}
    for rec in gsub.FeatureList.FeatureRecord:
        if rec.FeatureTag in ('init', 'medi'):
            feature_lookups[rec.FeatureTag] = rec.Feature.LookupListIndex

    for feat_tag, glyph_target in [('init', 'uni064A.init'), ('medi', 'uni064A.medi')]:
        for idx in feature_lookups.get(feat_tag, []):
            lookup = gsub.LookupList.Lookup[idx]
            for st in lookup.SubTable:
                if hasattr(st, 'mapping') and 'uni064A' in st.mapping:
                    st.mapping['uni0649'] = glyph_target


def compile_variable(source, path, italic):
    subprocess.run([sys.executable, '-m', 'fontmake', '-g', source, '-o', 'variable',
                    '--output-path', path, '--verbose', 'WARNING'], check=True)
    f = TTFont(path)
    unhinted(f)
    stat(f, italic)
    set_vertical_metrics(f)
    fix_arabic_shaping(f)
    set_version(f)
    f.save(path)


def build_static(vf_path, italic):
    os.makedirs(os.path.join(OUT, 'static'), exist_ok=True)
    for w, n in WEIGHTS:
        f = instancer.instantiateVariableFont(TTFont(vf_path), {'wght': w},
                                              overlap=instancer.OverlapMode.REMOVE, updateFontNames=True)
        style = ('' if n == 'Regular' and italic else n) + ('Italic' if italic else '')
        f.save(os.path.join(OUT, 'static', '%s-%s.ttf' % (FAMILY, style)))
    print('fonts/static/ (%s)' % ('italic' if italic else 'upright'))


def finish_variable(path, italic):
    """Name ID 25 goes in last: the instancer would use it as the static fonts' PostScript prefix."""
    f = TTFont(path)
    f['name'].setName(FAMILY + ('Italic' if italic else ''), 25, 3, 1, 0x409)
    f.save(path)
    f.flavor = 'woff2'
    f.save(path.replace('.ttf', '.woff2'))
    print('fonts/variable/' + os.path.basename(path))


if __name__ == '__main__':
    pin_timestamps(os.path.join(SRC, FAMILY + '.glyphs'))
    os.makedirs(os.path.join(OUT, 'variable'), exist_ok=True)
    for src, italic in ((FAMILY + '.glyphs', False), (FAMILY + '-Italic.glyphs', True)):
        vf = os.path.join(OUT, 'variable', FAMILY + ('-Italic' if italic else '') + '[wght].ttf')
        compile_variable(os.path.join(SRC, src), vf, italic)
        build_static(vf, italic)
        finish_variable(vf, italic)
