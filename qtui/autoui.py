# -*- coding: utf-8 -*-
"""
Created on Tue Jun 14 14:57:55 2016

@author: Arno Rehn
"""

from PyQt5 import QtWidgets
from .changeindicatorspinbox import ChangeIndicatorSpinBox
from .mplcanvas import MPLCanvas
import asyncio
from common import ComponentBase
from common.traits import DataSet as DataSetTrait
from traitlets import Instance, Float, Bool, Integer
from collections import OrderedDict
from itertools import chain


def run_action(func):
    ret = func()
    if asyncio.iscoroutine(ret):
        asyncio.ensure_future(ret)


def is_component_trait(x):
    return (isinstance(x, Instance) and issubclass(x.klass, ComponentBase))


def create_spinbox_entry(component, name, trait, datatype):
    def get_value():
        return trait.get(component)

    layout = QtWidgets.QHBoxLayout()
    spinbox = ChangeIndicatorSpinBox(is_double_spinbox=datatype is float,
                                     actual_value_getter=get_value)
    spinbox.setToolTip(trait.help)

    spinbox.setMinimum(-int('0x80000000', 16) if trait.min is None
                       else trait.min)
    spinbox.setMaximum(int('0x7FFFFFFF', 16) if trait.max is None
                       else trait.max)
    spinbox.setReadOnly(trait.read_only)

    unit = component.trait_metadata(name, 'unit', None)
    spinbox.setSuffix(unit and ' ' + unit)

    apply = QtWidgets.QToolButton()
    apply.setText('✓')
    apply.setAutoRaise(True)
    apply.setEnabled(not trait.read_only)
    layout.addWidget(spinbox)
    layout.addWidget(apply)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setStretch(0, 1)
    layout.setStretch(1, 0)

    def apply_value_to_component():
        setattr(component, name, spinbox.value())

    def apply_value_to_spinbox(change):
        spinbox.blockSignals(True)
        spinbox.setValue(change['new'])
        spinbox.blockSignals(False)

    spinbox.setValue(get_value())
    component.observe(apply_value_to_spinbox, name)

    if not trait.read_only:
        apply.clicked.connect(apply_value_to_component)
        apply.clicked.connect(spinbox.check_changed)
        spinbox.editingFinished.connect(apply_value_to_component)
        spinbox.editingFinished.connect(spinbox.check_changed)

    return layout


def create_checkbox(component, name, prettyName, trait):
    checkbox = QtWidgets.QCheckBox(prettyName)
    checkbox.setChecked(trait.get(component))
    checkbox.setEnabled(not trait.read_only)
    checkbox.setToolTip(trait.help)
    component.observe(lambda change: checkbox.setChecked(change['new']), name)
    if not trait.read_only:
        checkbox.toggled.connect(lambda toggled:
                                 setattr(component, name, toggled))

    return checkbox


def create_action(component, action):
    qaction = QtWidgets.QAction(action.metadata.get('name', action.__name__),
                                None)
    qaction.setToolTip(action.help)

    qaction.triggered.connect(lambda: run_action(action))

    return qaction


def create_plot_area(component, name, prettyName, trait):
    def draw(change):
        canvas.drawDataSet(change['new'],
                           trait.metadata.get('axes_labels', None),
                           trait.metadata.get('data_label', None),
                           trait.metadata.get('prefer_logscale', False))

    canvas = MPLCanvas()
    component.observe(draw, name)
    canvas.setTitle(prettyName)

    return canvas


def _group(trait):
    return trait.metadata.get('group', 'General')


def _prettyName(trait, name):
    return trait.metadata.get('name', name)


def generate_component_ui(name, component):
    controlWidget = QtWidgets.QWidget()

    # filter and sort traits
    traits = [(name, trait) for name, trait
              in sorted(component.traits().items(), key=lambda x: x[0])
              if not is_component_trait(trait)]

    # pre-create group boxes
    groups = OrderedDict()

    hasPlots = False
    for name, trait in chain(traits, component.actions):
        if isinstance(trait, DataSetTrait):
            hasPlots = True
            continue

        group = _group(trait)

        if group not in groups:
            box = QtWidgets.QGroupBox(group, controlWidget)
            QtWidgets.QFormLayout(box)
            groups[group] = box

    for name, trait in traits:
        if isinstance(trait, DataSetTrait):
            continue

        prettyName = _prettyName(trait, name)
        group = _group(trait)
        layout = groups[group].layout()

        if (isinstance(trait, Integer)):
            layout.addRow(prettyName + ": ",
                          create_spinbox_entry(component, name, trait, int))
        if (isinstance(trait, Float)):
            layout.addRow(prettyName + ": ",
                          create_spinbox_entry(component, name, trait, float))

    for name, trait in traits:
        if not isinstance(trait, Bool):
            continue
        prettyName = _prettyName(trait, name)
        group = _group(trait)

        layout = groups[group].layout()
        layout.addRow(None,
                      create_checkbox(component, name, prettyName, trait))

    for name, action in component.actions:
        group = _group(action)
        layout = groups[group].layout()
        qaction = create_action(component, action)
        qaction.setParent(controlWidget)
        btn = QtWidgets.QToolButton()
        btn.setDefaultAction(qaction)
        layout.addRow(None, btn)

    controlBox = QtWidgets.QVBoxLayout(controlWidget)
    controlBox.setContentsMargins(0, 0, 0, 0)
    for i, group in enumerate(groups.values()):
        controlBox.addWidget(group)
    controlBox.addStretch()

    if not hasPlots:
        return controlWidget

    plotWidget = QtWidgets.QWidget()
    plotBox = QtWidgets.QVBoxLayout(plotWidget)
    plotBox.setContentsMargins(0, 0, 0, 0)

    for name, trait in traits:
        if not isinstance(trait, DataSetTrait):
            continue
        prettyName = _prettyName(trait, name)

        plotBox.addWidget(create_plot_area(component, name, prettyName, trait))

    splitter = QtWidgets.QSplitter()
    splitter.addWidget(plotWidget)
    splitter.addWidget(controlWidget)
    splitter.setStretchFactor(0, 1)
    splitter.setStretchFactor(1, 0)
    splitter.setChildrenCollapsible(False)

    return splitter


def generate_ui(component):

    stack = QtWidgets.QStackedWidget()

    def make_tree_items(component, name, depth, treeitem):
        prettyName = component.objectName or name
        newItem = QtWidgets.QTreeWidgetItem(treeitem)
        newItem.setText(0, prettyName)
        newItem.setExpanded(True)

        widget = generate_component_ui(prettyName, component)
        newItem.widgetId = stack.addWidget(widget)

        for name, trait in component.attributes.items():
            if not is_component_trait(trait):
                continue
            cInst = getattr(component, name)
            make_tree_items(cInst, name, depth + 1, newItem)

    win = QtWidgets.QWidget()
    win.setWindowTitle(getattr(component, "title", "Taipan"))
    tree = QtWidgets.QTreeWidget(win)
    tree.setColumnCount(1)
    tree.setHeaderHidden(True)
    make_tree_items(component, "", 0, tree.invisibleRootItem())

    layout = QtWidgets.QHBoxLayout(win)
    splitter = QtWidgets.QSplitter()
    splitter.setChildrenCollapsible(False)
    layout.addWidget(splitter)

    splitter.addWidget(tree)
    splitter.addWidget(stack)
    tree.setSizePolicy(QtWidgets.QSizePolicy.Minimum,
                       QtWidgets.QSizePolicy.Minimum)
    splitter.setStretchFactor(0, 0)
    splitter.setStretchFactor(1, 1)

    tree.itemClicked.connect(lambda x: stack.setCurrentIndex(x.widgetId))

    return win
