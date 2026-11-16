#!/usr/bin/env python3
"""Render native four-layer CAM as top/bottom board and silkscreen previews.

This is a visualization helper, not a manufacturing or electrical checker.
It reads all four copper layers and merges both native plated-drill files.
"""
import argparse
import re
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cam', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()

    from gerbonara import GerberFile, ExcellonFile
    from gerbonara.layers import LayerStack
    import gi
    import cairo
    gi.require_version('Rsvg', '2.0')
    from gi.repository import Rsvg

    args.output.mkdir(exist_ok=True, parents=True)
    with zipfile.ZipFile(args.cam) as archive:
        entries = [n for n in archive.namelist() if not n.endswith('/')]

        def unique(predicate, description):
            matches = [n for n in entries if predicate(Path(n))]
            if len(matches) != 1:
                raise ValueError(f'Expected one {description}; found {matches}')
            return matches[0]

        layers = {}
        specifications = [
            ('top', 'copper', '.GTL'),
            ('inner1', 'copper', '.G1'),
            ('inner2', 'copper', '.G2'),
            ('bottom', 'copper', '.GBL'),
            ('top', 'silk', '.GTO'), ('bottom', 'silk', '.GBO'),
            ('top', 'mask', '.GTS'), ('bottom', 'mask', '.GBS'),
            ('top', 'paste', '.GTP'), ('mechanical', 'outline', '.GKO'),
        ]
        for side, use, extension in specifications:
            name = unique(lambda p: p.suffix.upper() == extension, extension)
            layers[side, use] = GerberFile.from_string(archive.read(name).decode())

        def drill(basename, plated):
            name = unique(lambda p: p.name == basename, basename)
            lines = []
            for line in archive.read(name).decode().splitlines():
                if 'G85' in line:
                    match = re.fullmatch(
                        r'(X[-+0-9.]+Y[-+0-9.]+)G85(X[-+0-9.]+Y[-+0-9.]+)', line)
                    if match is None:
                        raise ValueError(f'Unsupported Excellon slot statement: {line}')
                    # Preserve the original slot endpoints as a routed drill.
                    lines.extend(['G00' + match[1], 'M15', 'G01' + match[2], 'M16', 'G05'])
                else:
                    lines.append(line)
            return ExcellonFile.from_string('\n'.join(lines), plated=plated)

        plated = drill('Drill_PTH_Through.DRL', True)
        # The native ordinary-via drill file is separate from component PTHs.
        # Omitting this merge makes previews falsely display undrilled vias.
        plated.merge(drill('Drill_PTH_Through_Via.DRL', True))
        stack = LayerStack(
            layers, plated, drill('Drill_NPTH_Through.DRL', False),
            board_name='ESPaperPlay Native99')

        for side in ['top', 'bottom']:
            for mode in ['pretty', 'silk']:
                bounds = ((-1, -100), (100, 1))
                svg = (stack.to_pretty_svg(side=side, force_bounds=bounds)
                       if mode == 'pretty'
                       else layers[side, 'silk'].to_svg(force_bounds=bounds))
                path = args.output / (side + '-' + mode + '.svg')
                path.write_text(str(svg))
                surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 2600, 2600)
                context = cairo.Context(surface)
                rectangle = Rsvg.Rectangle()
                rectangle.x = rectangle.y = 0
                rectangle.width = rectangle.height = 2600
                Rsvg.Handle.new_from_file(str(path)).render_document(context, rectangle)
                surface.write_to_png(str(path.with_suffix('.png')))
                print(path, flush=True)


if __name__ == '__main__':
    main()
