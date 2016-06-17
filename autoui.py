# -*- coding: utf-8 -*-
"""
Created on Tue Jun 14 14:57:55 2016

@author: Arno Rehn
"""

from PyQt5 import QtCore, QtWidgets
import quamash
import asyncio
import sys
from common import ComponentBase, DataSet
from traitlets import Instance, Float, Bool, Integer
from test import AppRoot
from collections import OrderedDict
from itertools import chain


def run_action(func):
    ret = func()
    if asyncio.iscoroutine(ret):
        asyncio.ensure_future(ret)


def is_component_trait(x):
    return (isinstance(x, Instance) and issubclass(x.klass, ComponentBase))


def create_spinbox_entry(component, name, trait, datatype):
    layout = QtWidgets.QHBoxLayout()
    if datatype is float:
        spinbox = QtWidgets.QDoubleSpinBox()
    else:
        spinbox = QtWidgets.QSpinBox()

    spinbox.setToolTip(trait.help)
    spinbox.setMinimum(trait.min or -int('0x80000000', 16))
    spinbox.setMaximum(trait.max or int('0x7FFFFFFF', 16))

    unit = component.trait_metadata(name, 'unit', None)
    spinbox.setSuffix(unit and ' ' + unit)

    apply = QtWidgets.QToolButton()
    apply.setText('✓')
    apply.setAutoRaise(True)
    layout.addWidget(spinbox)
    layout.addWidget(apply)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setStretch(0, 1)
    layout.setStretch(1, 0)

    spinbox.setValue(trait.get(component))
    component.observe(lambda change: spinbox.setValue(change['new']), name)

    return layout


def create_checkbox(component, name, prettyName, trait):
    checkbox = QtWidgets.QCheckBox(prettyName)
    checkbox.setChecked(trait.get(component))
    checkbox.setEnabled(not trait.read_only)
    checkbox.setToolTip(trait.help)
    component.observe(lambda change: checkbox.setChecked(change['new']), name)

    return checkbox


def create_action(component, action):
    qaction = QtWidgets.QAction(action.metadata.get('name', action.__name__),
                                None)
    qaction.setToolTip(action.help)

    qaction.triggered.connect(lambda: run_action(action))

    return qaction


def _group(trait):
    return trait.metadata.get('group', 'General')


def _prettyName(trait, name):
    return trait.metadata.get('name', name)


def generate_component_ui(name, component):
    widget = QtWidgets.QWidget()

    # filter and sort traits
    traits = [(name, trait) for name, trait
              in sorted(component.traits().items(), key=lambda x: x[0])
              if not is_component_trait(trait)]

    # pre-create group boxes
    groups = OrderedDict()

    for name, trait in chain(traits, component.actions):
        group = _group(trait)

        if group not in groups:
            box = QtWidgets.QGroupBox(group, widget)
            QtWidgets.QFormLayout(box)
            groups[group] = box

    for name, trait in traits:
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
        qaction.setParent(widget)
        btn = QtWidgets.QToolButton()
        btn.setDefaultAction(qaction)
        layout.addRow(None, btn)

    grid = QtWidgets.QGridLayout(widget)
    grid.setContentsMargins(-1, 0, 0, 0)
    for i, group in enumerate(groups.values()):
        row = int(i / 2)
        col = i % 2
        grid.addWidget(group, row, col)

    return widget


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


app = QtWidgets.QApplication(sys.argv)
loop = quamash.QEventLoop(app)
asyncio.set_event_loop(loop)

root = AppRoot()

ui = generate_ui(root)
ui.show()

root.positioningVelocity = 20
root.scanVelocity = 5
root.maximumValue = 10
root.step = 0.5

with loop:
    sys.exit(loop.run_forever())
