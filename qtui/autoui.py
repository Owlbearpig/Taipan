# -*- coding: utf-8 -*-
"""
Created on Tue Jun 14 14:57:55 2016

@author: Arno Rehn
"""

from PyQt5 import QtWidgets, QtCore
from .changeindicatorspinbox import ChangeIndicatorSpinBox
from .changeindicatorlineedit import ChangeIndicatorLineEdit
from .mplcanvas import MPLCanvas
import asyncio
from common import ComponentBase
from common.traits import DataSet as DataSetTrait
from traitlets import Instance, Float, Bool, Integer, Enum, Unicode
from collections import OrderedDict
from itertools import chain
from common.traits import Quantity


def run_action(func):
    ret = func()
    if asyncio.iscoroutine(ret):
        asyncio.ensure_future(ret)


def is_component_trait(x):
    return (isinstance(x, Instance) and issubclass(x.klass, ComponentBase))


def create_spinbox_entry(component, name, trait):
    is_integer = isinstance(trait, Integer)

    def get_value_with_units():
        return trait.get(component).magnitude

    def get_value_without_units():
        return trait.get(component)

    get_value = (get_value_with_units if isinstance(trait, Quantity)
                 else get_value_without_units)

    layout = QtWidgets.QHBoxLayout()
    spinbox = ChangeIndicatorSpinBox(is_double_spinbox=not is_integer,
                                     actual_value_getter=get_value)
    spinbox.setToolTip(trait.help)

    if not is_integer:
        spinbox.setMinimum(float('-inf') if trait.min is None
                           else trait.min.magnitude)
        spinbox.setMaximum(float('inf') if trait.max is None
                           else trait.max.magnitude)
    else:
        spinbox.setMinimum(-2147483648 if trait.min is None else trait.min)
        spinbox.setMaximum(2147483647 if trait.max is None else trait.max)

    spinbox.setReadOnly(trait.read_only)

    if isinstance(trait, Quantity):
        units = (trait.metadata.get('preferred_units', None) or
                 trait.get(component).units)
        spinbox.setSuffix(" {:C~}".format(units))

    apply = QtWidgets.QToolButton()
    apply.setFocusPolicy(QtCore.Qt.NoFocus)
    apply.setText('✓')
    apply.setAutoRaise(True)
    apply.setEnabled(not trait.read_only)
    layout.addWidget(spinbox)
    layout.addWidget(apply)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setStretch(0, 1)
    layout.setStretch(1, 0)

    def apply_value_to_component_with_units():
        val = spinbox.value() * units
        setattr(component, name, val)

    def apply_value_to_component_without_units():
        setattr(component, name, spinbox.value())

    apply_value_to_component = \
        (apply_value_to_component_with_units if isinstance(trait, Quantity)
         else apply_value_to_component_without_units)

    def apply_value_to_spinbox_with_units(val):
        spinbox.blockSignals(True)
        spinbox.setValue(val.to(units).magnitude)
        spinbox.blockSignals(False)

    def apply_value_to_spinbox_without_units(val):
        spinbox.blockSignals(True)
        spinbox.setValue(val)
        spinbox.blockSignals(False)

    apply_value_to_spinbox = \
        (apply_value_to_spinbox_with_units if isinstance(trait, Quantity)
         else apply_value_to_spinbox_without_units)

    apply_value_to_spinbox(trait.get(component))
    component.observe(lambda c: apply_value_to_spinbox(c['new']), name)

    if not trait.read_only:
        apply.clicked.connect(apply_value_to_component)
        apply.clicked.connect(spinbox.check_changed)
        spinbox.editingFinished.connect(apply_value_to_component)
        spinbox.editingFinished.connect(spinbox.check_changed)

    return layout


def create_progressbar(component, name, trait):
    progressBar = QtWidgets.QProgressBar()
    progressBar.setMinimum(trait.min * 1000)
    progressBar.setMaximum(trait.max * 1000)
    progressBar.setValue(trait.get(component) * 1000)
    component.observe(
        lambda change: progressBar.setValue(change['new'] * 1000),
        name
    )

    return progressBar


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
        canvas.dataIsPower = trait.metadata.get('is_power', False)
        canvas.drawDataSet(change['new'],
                           trait.metadata.get('axes_labels', None),
                           trait.metadata.get('data_label', None))

    canvas = MPLCanvas()
    component.observe(draw, name)
    canvas.setTitle(prettyName)

    return canvas


def create_combobox(component, name, trait):
    combobox = QtWidgets.QComboBox()
    for item in trait.values:
        combobox.addItem(item.name, item)

    combobox.setCurrentText(trait.get(component).name)

    component.observe(lambda change:
                      combobox.setCurrentText(change['new'].name), name)

    combobox.currentIndexChanged.connect(
        lambda: setattr(component, name, combobox.currentData())
    )

    return combobox


def create_label(component, name, trait):
    label = QtWidgets.QLabel()
    label.setText(trait.get(component))

    component.observe(lambda change: label.setText(change['new']), name)

    return label


def create_lineedit(component, name, trait):
    lineEdit = ChangeIndicatorLineEdit(actual_value_getter=
                                       lambda: trait.get(component))
    lineEdit.setText(trait.get(component))

    def apply_text_to_lineedit(change):
        lineEdit.blockSignals(True)
        lineEdit.setText(change['new'])
        lineEdit.blockSignals(False)

    def apply_text_to_component():
        setattr(component, name, lineEdit.text())

    component.observe(apply_text_to_lineedit, name)
    lineEdit.editingFinished.connect(apply_text_to_component)
    lineEdit.editingFinished.connect(lineEdit.check_changed)

    return lineEdit


def _group(trait):
    return trait.metadata.get('group', 'General')


def _prettyName(trait, name):
    return trait.metadata.get('name', name)


traitPriority = {
    'Unicode': 0,
    'Float': 1,
    'Int': 1,
    'Quantity': 1,
    'Enum': 2,
    'Bool': 7,
    'Float_readonly': 10
}


def _traitSortingKey(args):
    name, trait = args
    traittype = type(trait).__name__
    traittype_ro = traittype + "_readonly"

    prio = traitPriority.get(traittype_ro, None)
    if prio is None:
        prio = traitPriority.get(traittype, None)
    if prio is None:
        prio = 999

    userPrio = trait.metadata.get('priority', 999)

    return prio, userPrio, name


def generate_component_ui(name, component):
    controlWidget = QtWidgets.QWidget()

    # filter and sort traits
    traits = [(name, trait) for name, trait
              in sorted(chain(component.traits().items(),
                              component.actions), key=_traitSortingKey)
              if not is_component_trait(trait)]

    # pre-create group boxes
    groups = OrderedDict()

    hasPlots = False
    for name, trait in traits:
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

        if (isinstance(trait, Quantity)):
            layout.addRow(prettyName + ": ",
                          create_spinbox_entry(component, name, trait))
        if (isinstance(trait, Integer)):
            layout.addRow(prettyName + ": ",
                          create_spinbox_entry(component, name, trait))
        elif isinstance(trait, Enum) and not trait.read_only:
            layout.addRow(prettyName + ": ",
                          create_combobox(component, name, trait))
        elif isinstance(trait, Float) and trait.read_only:
            layout.addRow(prettyName + ": ",
                          create_progressbar(component, name, trait))
        elif isinstance(trait, Bool):
            layout.addRow(None,
                          create_checkbox(component, name, prettyName, trait))
        elif isinstance(trait, Unicode):
            if trait.read_only:
                layout.addRow(name + ": ",
                              create_label(component, name, trait))
            else:
                layout.addRow(name + ": ",
                              create_lineedit(component, name, trait))
        elif callable(trait):
            qaction = create_action(component, trait)
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

        for name, trait in sorted(component.attributes.items(),
                                  key=lambda x: x[0]):
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

    layout = QtWidgets.QVBoxLayout(win)
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

    messagePane = QtWidgets.QGroupBox("Messages", win)
    layout.addWidget(messagePane)
    messagePane.setCheckable(True)

    msgPaneLayout = QtWidgets.QVBoxLayout(messagePane)
    msgBrowser = QtWidgets.QTextBrowser(messagePane)
    msgPaneLayout.addWidget(msgBrowser)

    messagePane.toggled.connect(msgBrowser.setVisible)

    layout.setStretch(0, 1)
    layout.setStretch(1, 0)

    return win, msgBrowser
