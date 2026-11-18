#!/usr/bin/env python3
"""Match the planned native library outline revision to the actual top silkscreen Gerber."""
import argparse
from collections import Counter, defaultdict
import hashlib
import itertools
import json
from pathlib import Path
import zipfile

from gerbonara.rs274x import GerberFile
from shapely.affinity import rotate, translate
from shapely.ops import unary_union
from shapely.strtree import STRtree

import native_source_geometry as ng
from check_native_silkscreen import object_geometry

# Bounds on the native path / swept Gerber tessellations and export quantization.
# Unchanged Gerber drawing instructions are compared separately without tolerance.
TOLERANCE_MM = 0.00008


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gerber_objects(cam):
    with zipfile.ZipFile(cam) as archive:
        names = [n for n in archive.namelist() if n.upper().endswith('.GTO')]
        if len(names) != 1:
            raise ValueError(f'Expected one top silkscreen file in {cam}')
        drawing = GerberFile.from_string(archive.read(names[0]).decode())
    if not all(obj.polarity_dark for obj in drawing.objects):
        raise ValueError('The multiset check requires a dark-only top silkscreen')
    return drawing.objects


def first_cover(shape, polygons, indices):
    """Allow one native stroke to be split into several actual Gerber objects."""
    if len(indices) > 12:
        raise ValueError('Ambiguous Gerber attribution')
    for count in range(1, len(indices) + 1):
        for group in itertools.combinations(indices, count):
            ink = unary_union([polygons[i] for i in group])
            if ink.buffer(TOLERANCE_MM, quad_segs=8).covers(shape):
                return group
    return ()


def attribute(cam, changes, which, placements):
    objects = gerber_objects(cam)
    polygons = [object_geometry(obj) for obj in objects]
    index = STRtree(polygons)
    used = set()
    matches = []
    errors = []
    for change in changes:
        body = change[which]
        if body is None or body['layerId'] != 3:
            continue
        if change['kind'] != 'POLY' or not placements.get(change['fp']):
            raise ValueError('Expected a placed native library polyline')
        template = ng.path_line(body['path']).buffer(body['width'] * ng.MM / 2, quad_segs=1024)
        for ref, pose in placements[change['fp']]:
            shape = translate(rotate(template, pose['angle'], origin=(0, 0)),
                              pose['x'] * ng.MM, pose['y'] * ng.MM)
            region = shape.buffer(TOLERANCE_MM, quad_segs=8)
            candidates = [int(i) for i in index.query(region)
                          if i not in used and region.covers(polygons[i])]
            covered = first_cover(shape, polygons, candidates)
            record = {'ref': ref, 'library_record': change['id']}
            if covered:
                used.update(covered)
                matches.append(dict(record, gto_object_indices=covered))
            else:
                errors.append(dict(record, candidate_indices=candidates, expected_bounds_mm=shape.bounds))
    unmatched = Counter(tuple(map(repr, obj.to_primitives())) for i, obj in enumerate(objects)
                        if i not in used)
    return {'total_actual_objects': len(objects), 'matched_native_strokes': len(matches),
            'matched_actual_objects': len(used), 'matches': matches, 'errors': errors}, unmatched


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ['baseline-cam', 'revised-cam', 'source', 'plan', 'output']:
        parser.add_argument('--' + arg, type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    if digest(args.baseline_cam) != plan['baseline_cam_sha256']:
        raise ValueError('Wrong baseline CAM for supplied edit plan')
    _, source, _ = ng.archive_helper.load_snapshot(args.source)
    placements = defaultdict(list)
    for ref, binding in ng.archive_helper.component_index(source).items():
        placements[binding['footprint_uuid']].append((ref, source['COMPONENT', binding['component_id']]))
    old, old_other = attribute(args.baseline_cam, plan['changes'], 'before', placements)
    new, new_other = attribute(args.revised_cam, plan['changes'], 'after', placements)
    unexpected_removed = old_other - new_other
    unexpected_added = new_other - old_other
    passed = not (old['errors'] or new['errors'] or unexpected_added or unexpected_removed)
    result = {
        'status': 'PASS_ACTUAL_GTO_LIBRARY_EDIT_SCOPE' if passed else 'FAIL',
        'inputs': {key: digest(getattr(args, key))
                   for key in ['baseline_cam', 'revised_cam', 'source', 'plan']},
        'checker_sha256': digest(Path(__file__)), 'tolerance_mm_for_native_attribution': TOLERANCE_MM,
        'original': old, 'revised': new, 'unchanged_actual_object_count': sum((old_other & new_other).values()),
        'unexpected_removed': dict((str(k), v) for k, v in unexpected_removed.items()),
        'unexpected_added': dict((str(k), v) for k, v in unexpected_added.items()),
        'scope': 'Each changed printed library stroke on every instance matches the actual Gerber ink '
                 'in both geometric directions within the published tolerance. Each drawing object is used '
                 'at most once per side. All other expanded Gerber primitives and their multiplicities must '
                 'match exactly. Primitive order is immaterial for dark-only artwork.',
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'], 'original/revised strokes:', len(old['matches']), len(new['matches']),
          'unaffected:', result['unchanged_actual_object_count'], 'unmatched:', len(old['errors']), len(new['errors']))
    return int(not passed)


if __name__ == '__main__':
    raise SystemExit(main())
