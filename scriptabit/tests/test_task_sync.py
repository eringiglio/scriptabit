# -*- coding: utf-8 -*-
from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)
from builtins import *
import json
import pytest
import requests
import requests_mock
import uuid

from pkg_resources import resource_filename
from random import randint, choice

from bidict import (
    KeyDuplicationError,
    ValueDuplicationError,
    KeyAndValueDuplicationError)
from tempfile import NamedTemporaryFile
from scriptabit import (
    SyncStatus,
    TaskSync,
    Task,
    TaskMap,
    Difficulty,
    CharacterAttribute)

from .task_implementations import TestTaskService, TestTask


difficulties = (
    Difficulty.trivial,
    Difficulty.easy,
    Difficulty.medium,
    Difficulty.hard)

attributes = (
    CharacterAttribute.strength,
    CharacterAttribute.intelligence,
    CharacterAttribute.constitution,
    CharacterAttribute.perception)

def random_task():
    t = TestTask(_id=uuid.uuid4())
    t.name = uuid.uuid1()
    t.description = 'blah blah tired blah coffee'
    t.completed = choice((True, False))
    t.difficulty = difficulties[randint(0,len(difficulties)-1)]
    t.attribute = attributes[randint(0,len(attributes)-1)]
    t.status = SyncStatus.unchanged
    return t

def test_new_tasks():
    src_tasks = [random_task() for x in range(3)]
    dst_tasks = []
    src = TestTaskService(src_tasks)
    dst = TestTaskService(dst_tasks)
    map = TaskMap()
    sync = TaskSync(src, dst, map)
    sync.synchronise()

    assert len(dst.persisted_tasks) == len(src_tasks)
    for d in dst.persisted_tasks:
        assert d.status == SyncStatus.new
        assert d in dst_tasks
        assert map.try_get_src_id(d.id)

    for s in src.get_all_tasks():
        dst_id = map.try_get_dst_id(s.id)
        assert dst_id
        d = dst.get_task(dst_id)
        assert s.name == d.name
        assert s.description == d.description
        assert s.completed == d.completed
        assert s.difficulty == d.difficulty
        assert s.attribute == d.attribute

def test_new_tasks_are_mapped():
    src_tasks = [random_task()]
    dst_tasks = []
    src = TestTaskService(src_tasks)
    dst = TestTaskService(dst_tasks)
    map = TaskMap()
    sync = TaskSync(src, dst, map)

    # preconditions
    assert len(map.get_all_src_keys()) == 0

    sync.synchronise()

    assert len(map.get_all_src_keys()) == 1
    assert src_tasks[0].id in map.get_all_src_keys()
    assert map.get_dst_id(src_tasks[0].id) == dst_tasks[0].id

def test_missing_mapped_destination_tasks():
    """ Tests expected behaviours on mapped tasks that are missing in
    the destination.
    """
    src = random_task()
    src_tasks = [src]
    src_svc = TestTaskService(src_tasks)

    dst = random_task()
    dst_tasks = []
    dst_svc = TestTaskService(dst_tasks)

    map = TaskMap()

    # create the pre-existing mapping
    map.map(src, dst)

    # preconditions
    assert len(map.get_all_src_keys()) == 1
    assert map.get_dst_id(src.id) == dst.id
    assert map.get_src_id(dst.id) == src.id

    sync = TaskSync(src_svc, dst_svc, map)
    sync.synchronise()

    assert len(map.get_all_src_keys()) == 1, "should still be just one mapping"
    assert not map.try_get_src_id(dst.id), "old dst should be unmapped"
    assert map.get_dst_id(src.id) != dst.id, "src should be mapped to something else"
    assert dst_svc.tasks[0].status == SyncStatus.new, "should be flagged as a new task"
    assert len(dst_svc.tasks) == 1, "just one dst task"

def test_existing_tasks_are_updated():
    src = random_task()
    src.difficulty = Difficulty.hard
    src.attribute = CharacterAttribute.strength
    src_tasks = [src]
    src_svc = TestTaskService(src_tasks)
    dst = random_task()
    dst.description = 'something different'
    dst.difficulty = Difficulty.medium
    dst.attribute = CharacterAttribute.constitution
    dst_tasks = [dst]
    dst_svc = TestTaskService(dst_tasks)

    # precondition tests
    assert src.id != dst.id
    assert src.status == SyncStatus.unchanged
    assert dst.name != src.name
    assert dst.attribute != src.attribute
    assert dst.difficulty != src.difficulty
    assert dst.status == SyncStatus.unchanged
    assert dst.description != src.description
    map = TaskMap()
    map.map(src, dst)

    sync = TaskSync(src_svc, dst_svc, map)
    sync.synchronise()

    assert len(dst_svc.persisted_tasks) == 1
    actual = dst_svc.persisted_tasks[0]
    assert actual.id == dst.id, "id not changed"
    assert actual.id != src.id, "id not changed"
    assert actual.name == src.name
    assert actual.attribute == src.attribute
    assert actual.difficulty == src.difficulty
    assert actual.completed == src.completed
    assert actual.status == SyncStatus.updated
    assert actual.description == src.description

def test_deleted_src_tasks():
    src_tasks = []
    dst = random_task()
    dst_tasks = [dst]
    ss = TestTaskService(src_tasks)
    ds = TestTaskService(dst_tasks)
    map = TaskMap()

    # we need to create a mapping between a src task and dst, but leave
    # the source task out of the source service
    src = random_task()
    map.map(src, dst)

    sync = TaskSync(ss, ds, map)

    # preconditions
    assert len(ss.tasks) == 0
    assert len(ds.tasks) == 1
    assert dst.status == SyncStatus.unchanged

    sync.synchronise()

    # the task list lengths should not be changed
    assert len(ss.tasks) == 0
    assert len(ds.tasks) == 1

    # dst should now be flagged as deleted
    assert dst.status == SyncStatus.deleted

def test_remove_orphan_mappings():
    src_tasks = [random_task()]
    dst_tasks = []
    ss = TestTaskService(src_tasks)
    ds = TestTaskService(dst_tasks)
    map = TaskMap()

    # add a few task mappings that won't exist in either source or destination
    map.map(random_task(), random_task())
    map.map(random_task(), random_task())
    map.map(random_task(), random_task())

    TaskSync(ss, ds, map).synchronise(clean_orphans=True)

    # We now expect just one mapping for the new src task
    all_mappings = map.get_all_src_keys()
    assert len(all_mappings) == 1
    assert map.get_dst_id(src_tasks[0].id)