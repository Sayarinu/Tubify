from PySide6.QtCore import QCoreApplication, QModelIndex, Qt
from PySide6.QtTest import QAbstractItemModelTester

from youtube_music_native.catalog.page_model import PageModel


def tracked(snapshots=False):
    QCoreApplication.instance() or QCoreApplication([])
    model = PageModel(snapshots=snapshots)
    model.tester = QAbstractItemModelTester(model, QAbstractItemModelTester.FailureReportingMode.Fatal)
    events = []
    model.modelReset.connect(lambda: events.append("reset"))
    model.rowsInserted.connect(lambda parent, first, last: events.append(("insert", first, last)))
    model.rowsRemoved.connect(lambda parent, first, last: events.append(("remove", first, last)))
    model.dataChanged.connect(lambda first, last, roles: events.append(("change", first.row(), last.row())))
    return model, events


def rows(model):
    return [model.index(row).data(PageModel.ROW) for row in range(model.rowCount())]


def titles(*values):
    return [{"title": value} for value in values]


def test_rows_reach_qml_as_model_data():
    model, events = tracked()
    assert list(model.roleNames().values()) == [b"modelData"] and model.rowCount(model.index(0)) == 0
    model.sync(titles("a"))
    assert rows(model) == titles("a")
    assert model.index(0).data(Qt.ItemDataRole.DisplayRole) is None


def test_appending_inserts_only_the_new_rows():
    model, events = tracked()
    first = titles("a", "b")
    model.sync(first)
    events.clear()
    model.sync(first + titles("c", "d"))
    assert events == [("insert", 2, 3)] and rows(model) == titles("a", "b", "c", "d")


def test_unchanged_rows_signal_nothing_even_as_new_objects():
    model, events = tracked()
    model.sync(titles("a", "b"))
    events.clear()
    model.sync(titles("a", "b"))
    assert events == []


def test_changes_removals_and_insertions_touch_only_those_rows():
    model, events = tracked()
    model.sync(titles("a", "b", "c", "d"))
    events.clear()
    model.sync(titles("a", "B", "c", "d"))
    assert events == [("change", 1, 1)]
    events.clear()
    model.sync(titles("a", "c", "d"))
    assert events == [("remove", 1, 1)] and rows(model) == titles("a", "c", "d")
    events.clear()
    model.sync(titles("z", "a", "c", "d"))
    assert events == [("insert", 0, 0)] and rows(model) == titles("z", "a", "c", "d")
    events.clear()
    # Repeated rows match from both ends without overlapping.
    model.sync(titles("z", "a", "c", "d", "d"))
    assert events == [("insert", 4, 4)] and rows(model) == titles("z", "a", "c", "d", "d")
    events.clear()
    model.sync([])
    assert events == [("remove", 0, 4)] and rows(model) == []


def test_a_replaced_middle_changes_what_it_can_and_resizes_the_rest():
    model, events = tracked()
    model.sync(titles("a", "b", "c", "d"))
    events.clear()
    model.sync(titles("a", "x", "d"))
    assert events == [("change", 1, 1), ("remove", 2, 2)] and rows(model) == titles("a", "x", "d")
    events.clear()
    model.sync(titles("a", "p", "q", "r", "d"))
    assert events == [("change", 1, 1), ("insert", 2, 3)] and rows(model) == titles("a", "p", "q", "r", "d")


def test_reset_starts_afresh():
    model, events = tracked()
    model.sync(titles("a"))
    events.clear()
    model.sync(titles("a", "b"), reset=True)
    assert events == ["reset"] and rows(model) == titles("a", "b")


def test_edits_in_place_need_touched_and_then_refresh_the_rows():
    model, events = tracked()
    values = titles("a", "b")
    model.sync(values)
    events.clear()
    values[1]["title"] = "B"
    model.sync(values)
    assert events == []  # The model shares the rows, so it cannot see this edit by itself.
    model.sync(values, touched=True)
    assert events == [("change", 0, 1)] and rows(model) == titles("a", "B")
    # After equal rows arrive as new objects, in-place edits to those still reach the model.
    fresh = titles("a", "B")
    model.sync(fresh)
    fresh[0]["title"] = "A"
    assert rows(model) == titles("A", "B")


def test_snapshots_find_the_rows_changed_in_place():
    model, events = tracked(snapshots=True)
    shelves = [{"title": "one", "items": titles("a")}, {"title": "two", "items": titles("b")}]
    model.sync(shelves)
    events.clear()
    model.sync(shelves)
    assert events == []
    shelves[1]["items"][0]["title"] = "B"
    assert rows(model)[1]["items"][0]["title"] == "b"
    model.sync(shelves)
    assert events == [("change", 1, 1)] and rows(model)[1]["items"][0]["title"] == "B"
    events.clear()
    model.sync(shelves + [{"title": "three", "items": []}])
    assert events == [("insert", 2, 2)] and rows(model)[2]["title"] == "three"
