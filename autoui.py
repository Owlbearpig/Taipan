# -*- coding: utf-8 -*-
"""
Created on Tue Jun 14 14:57:55 2016

@author: Arno Rehn
"""

from PyQt5 import QtCore, QtWidgets
import sys
from common import ComponentBase, DataSet
from scan import Scan
from traitlets import Instance, Float, Bool, Integer
from test import AppRoot


def is_component_trait(x):
    return (isinstance(x, Instance) and issubclass(x.klass, ComponentBase))


def create_spinbox_entry(component, name, trait, datatype):
    layout = QtWidgets.QHBoxLayout()
    if datatype is float:
        spinbox = QtWidgets.QDoubleSpinBox()
    else:
        spinbox = QtWidgets.QSpinBox()

    spinbox.setToolTip(component.traits()[name].help)
    spinbox.setMinimum(component.traits()[name].min or -int('0x80000000', 16))
    spinbox.setMaximum(component.traits()[name].max or int('0x7FFFFFFF', 16))

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

    spinbox.setValue(getattr(component, name))
    component.observe(lambda change: spinbox.setValue(change['new']), name)

    return layout


def generate_component_ui(name, component):
    widget = QtWidgets.QWidget()
    layout = QtWidgets.QFormLayout(widget)

    for name, trait in sorted(component.traits().items(), key=lambda x: x[0]):
        if (is_component_trait(trait)):
            continue  # skip sub-components

        prettyName = component.trait_metadata(name, 'name', name)

        if (isinstance(trait, Integer)):
            layout.addRow(prettyName + ": ",
                          create_spinbox_entry(component, name, trait, int))
        if (isinstance(trait, Float)):
            layout.addRow(prettyName + ": ",
                          create_spinbox_entry(component, name, trait, float))

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

root = AppRoot()

ui = generate_ui(root)
ui.show()

root.positioningVelocity = 20

sys.exit(app.exec_())
