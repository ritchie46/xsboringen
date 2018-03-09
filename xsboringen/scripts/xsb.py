# -*- coding: utf-8 -*-
# Royal HaskoningDHV

from xsboringen import cross_section
from xsboringen.calc import SandmedianClassifier, AdmixClassifier, LithologyClassifier
from xsboringen.csvfiles import boreholes_to_csv, cross_section_to_csv
from xsboringen.datasources import boreholes_from_sources, points_from_sources
from xsboringen import plot as xsplot
from xsboringen import shapefiles
from xsboringen import styles

import click
import yaml

from collections import ChainMap
from pathlib import Path
import logging
import os

log = logging.getLogger(os.path.basename(__file__))


def write_csv(**kwargs):
    # args
    datasources = kwargs['datasources']
    result = kwargs['result']
    config = kwargs['config']

    # read boreholes and CPT's from data folders
    admixclassifier = AdmixClassifier(
        config['admix_fieldnames']
        )
    borehole_sources = datasources.get('boreholes') or []
    boreholes = boreholes_from_sources(borehole_sources, admixclassifier)

    # translate CPT to lithology if needed
    if result.get('translate_cpt', False):
        table = config['cpt_classification']
        lithologyclassifier = LithologyClassifier(table)
        boreholes = (
            b.to_lithology(lithologyclassifier, admixclassifier)
            for b in boreholes
            )

    # classify sandmedian if needed
    if result.get('classify_sandmedian', False):
        bins = config['sandmedianbins']
        sandmedianclassifier = SandmedianClassifier(bins)
        boreholes = (
            b.update_sandmedianclass(sandmedianclassifier) for b in boreholes
            )

    # simplify if needed
    if result.get('simplify', False):
        min_thickness = result.get('min_thickness')
        boreholes = (
            b.simplified(min_thickness=min_thickness) for b in boreholes
            )

    # write output to csv
    extra_fields = result.get('extra_fields') or {}
    extra_fields = {k: tuple(v) for k, v in extra_fields.items()}
    boreholes_to_csv(boreholes, result['csvfile'],
        extra_fields=extra_fields,
        )


def write_shape(**kwargs):
    # args
    datasources = kwargs['datasources']
    result = kwargs['result']
    config = kwargs['config']

    # read boreholes and CPT's from data folders
    admixclassifier = AdmixClassifier(
        config['admix_fieldnames']
        )
    borehole_sources = datasources.get('boreholes') or []
    boreholes = boreholes_from_sources(borehole_sources, admixclassifier)

    # write output to shapefile
    shape_fields=result.get('shape_fields') or []
    shapefiles.boreholes_to_shape(boreholes, result['shapefile'],
        fields=shape_fields,
        **config['shapefile'],
        )


def plot(**kwargs):
    # args
    datasources = kwargs['datasources']
    cross_section_lines = kwargs['cross_section_lines']
    result = kwargs['result']
    config = kwargs['config']

    # optional args
    min_depth = kwargs.get('min_depth', 0.)
    buffer_distance = kwargs.get('buffer_distance', 0.)
    xtickstep = kwargs.get('xtickstep')
    ylim = kwargs.get('ylim')
    xlabel = kwargs.get('xlabel')
    ylabel = kwargs.get('ylabel')

    # create image folder
    folder = Path(result['folder'])
    folder.mkdir(exist_ok=True)

    # read boreholes and CPT's from data folders
    admixclassifier = AdmixClassifier(
        config['admix_fieldnames']
        )
    borehole_sources = datasources.get('boreholes') or []
    boreholes = boreholes_from_sources(borehole_sources, admixclassifier)

    # segment styles lookup
    segmentstyles = styles.SegmentStylesLookup(**config['styles']['segments'])

    # vertical styles lookup
    verticalstyles = styles.SimpleStylesLookup(**config['styles']['verticals'])

    # surface styles lookup
    surfacestyles = styles.SimpleStylesLookup(**config['styles']['surfaces'])

    # solid styles lookup
    solidstyles = styles.SimpleStylesLookup(**config['styles']['solids'])

    # translate CPT to lithology if needed
    if result.get('translate_cpt', False):
        table = config['cpt_classification']
        lithologyclassifier = LithologyClassifier(table)
        boreholes = (
            b.to_lithology(lithologyclassifier, admixclassifier)
            for b in boreholes
            )

    # classify sandmedian if needed
    if result.get('classify_sandmedian', False):
        bins = config['sandmedianbins']
        sandmedianclassifier = SandmedianClassifier(bins)
        boreholes = (
            b.update_sandmedianclass(sandmedianclassifier) for b in boreholes
            )

    # simplify if needed
    if result.get('simplify', False):
        min_thickness = result.get('min_thickness')
        groupby = lambda s: {'record': segmentstyles.lookup(s)}
        boreholes = (
            b.simplified(min_thickness=min_thickness, by=groupby)
            for b in boreholes
            )

    # read points
    point_sources = datasources.get('points') or []
    points = points_from_sources(point_sources)

    # surfaces
    surfaces = datasources.get('surfaces') or []

    # solids
    solids = datasources.get('solids') or []

    # filter missing coordinates and less than minimal depth
    boreholes = [
        b for b in boreholes
        if
        (b.x is not None) and
        (b.y is not None) and
        (b.z is not None) and
        (b.depth is not None) and
        (b.depth >= min_depth)
        ]

    points = [
        p for p in points
        if
        (p.x is not None) and
        (p.y is not None) and
        (p.z is not None) and
        ((p.top is not None) or (p.base is not None))
        ]

    # definest styles lookup
    plotting_styles = {
        'segments': segmentstyles,
        'verticals': verticalstyles,
        'surfaces': surfacestyles,
        'solids': solidstyles,
        }

    # default labels
    defaultlabels = iter(config['defaultlabels'])

    # selected set
    selected = cross_section_lines.get('selected')
    if selected is not None:
        selected = set(selected)

    css = []
    for row in shapefiles.read(cross_section_lines['file']):
        line_geometry = row['geometry']
        line_properties = row['properties']

        # get label
        if cross_section_lines.get('labelfield') is not None:
            label = line_properties[cross_section_lines['labelfield']]
        else:
            label = next(defaultlabels)

        if (selected is not None) and (label not in selected):
            log.warning('skipping {label:}'.format(label=label))
            continue

        # log message
        log.info('cross-section {label:}'.format(label=label))

        # define cross-section
        cs = cross_section.CrossSection(
            geometry=line_geometry,
            label=label,
            buffer_distance=buffer_distance,
            )

        # add boreholes to cross-section
        cs.add_boreholes(boreholes)

        # add points to cross_section
        cs.add_points(points)

        # add surfaces to cross-section
        for surface in surfaces:
            cs.add_surface(surface)

        # add solids to cross-section
        for solid in solids:
            cs.add_solid(solid)

        # define plot
        plt = xsplot.CrossSectionPlot(
            cross_section=cs,
            config=config['cross_section_plot'],
            styles=plotting_styles,
            xtickstep=xtickstep,
            ylim=ylim,
            xlabel=xlabel,
            ylabel=ylabel,
            )

        # plot and save to PNG file
        imagefilename = config['image_filename_format'].format(label=label)
        imagefile = folder / imagefilename
        log.info('saving {f.name:}'.format(f=imagefile))
        plt.to_image(str(imagefile))

        # save to CSV file
        csvfilename = config['csv_filename_format'].format(label=label)
        csvfile = folder / csvfilename
        log.info('saving {f.name:}'.format(f=csvfile))
        extra_fields = result.get('extra_fields') or {}
        extra_fields = {k: tuple(v) for k, v in extra_fields.items()}
        cross_section_to_csv(cs, str(csvfile),
            extra_fields=extra_fields,
            )

        # collect cross-sections
        css.append(cs)

    # export endpoints
    endpointsfile = folder / 'endpoints.shp'
    shapefiles.export_endpoints(str(endpointsfile), css,
        **config['shapefile'],
        )

    # export projection lines
    projectionlinesfile = folder / 'projectionlines.shp'
    shapefiles.export_projectionlines(str(projectionlinesfile), css,
        **config['shapefile'],
        )


def get_logging(level):
    return {
        'debug': logging.DEBUG,
        'info': logging.INFO,
        'warning': logging.WARNING,
        }.get(level, logging.DEBUG)


@click.command()
@click.argument('function',
    type=click.Choice(['write_csv', 'write_shape', 'plot']),
    )
@click.argument('inputfile',
    )
@click.option('--logging', 'logging_level',
    type=click.Choice(['warning', 'info', 'debug']),
    default='info',
    help='log messages level'
    )
def main(function, inputfile, logging_level):
    '''plot geological cross-sections'''
    logging.basicConfig(level=get_logging(logging_level))

    # function arguments from input file
    with open(inputfile) as y:
        f_kwargs = yaml.load(y)

    # read default config
    scripts_folder = os.path.dirname(os.path.realpath(__file__))
    defaultconfigfile = os.path.join(os.path.dirname(scripts_folder),
        'defaultconfig.yaml')
    with open(defaultconfigfile) as y:
        defaultconfig = yaml.load(y)

    # get user config from input file
    userconfig = f_kwargs.get('config') or {}

    # chain config
    f_kwargs['config'] = ChainMap(userconfig, defaultconfig)

    # dispatch function
    if function == 'write_csv':
        write_csv(**f_kwargs)
    elif function == 'write_shape':
        write_shape(**f_kwargs)
    elif function == 'plot':
        plot(**f_kwargs)


if __name__ == '__main__':
    main()