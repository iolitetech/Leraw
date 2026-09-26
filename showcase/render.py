"""Render the showcase pages to the README images.

    python showcase/render.py              # Playwright's Chromium
    python showcase/render.py msedge       # or an installed browser channel (msedge, chrome)

showcase/NAME.html -> images/NAME.png, showcase/ckb/NAME.html -> images/ckb/NAME.png, at 2x.
The pages load the fonts from fonts/variable, so run build.py first.
"""
import functools
import http.server
import os
import sys
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES = [('', 'images'), ('ckb', os.path.join('images', 'ckb'))]


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main(channel=None):
    handler = functools.partial(Quiet, directory=ROOT)
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = 'http://127.0.0.1:%d/showcase/' % server.server_address[1]
    with sync_playwright() as p:
        # grey anti-aliasing, so renders look the same on every OS and have no colour fringes
        browser = p.chromium.launch(channel=channel, args=['--disable-lcd-text', '--force-color-profile=srgb'])
        page = browser.new_page(viewport={'width': 1920, 'height': 1080}, device_scale_factor=2)
        for sub, out in PAGES:
            os.makedirs(os.path.join(ROOT, out), exist_ok=True)
            for name in sorted(os.listdir(os.path.join(ROOT, 'showcase', sub))):
                if not name.endswith('.html'):
                    continue
                page.goto(base + (sub + '/' if sub else '') + name)
                page.evaluate('document.fonts.ready')
                failed = page.evaluate('[...document.fonts].filter(f => f.status !== "loaded").length')
                if failed:
                    raise SystemExit('%s: fonts did not load (run build.py first)' % name)
                png = os.path.join(out, name.replace('.html', '.png'))
                page.locator('body > div').first.screenshot(path=os.path.join(ROOT, png))
                print(png.replace(os.sep, '/'))
        browser.close()
    server.shutdown()


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else None)
