"""Offline configured smithing plan and one-round adapter contracts."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from crafting_logic import completion_plan
from crafting_adapter import CraftingAdapter, CraftingResolver, SPECS
from write_guard import Refused, UncertainWrite


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.tiers=[dict(tier_id=1,score_min=0),dict(tier_id=2,score_min=600),dict(tier_id=3,score_min=1200)]
        self.effects=[dict(element=1,pool_id=1,required=15,activated=False),dict(element=1,pool_id=2,required=30,activated=True),dict(element=2,pool_id=3,required=20,activated=False)]
        self.energies={1:dict(value=10,address=0x1000),2:dict(value=40,address=0x2000)}

    def plan(self,score=200):
        return completion_plan(score,self.tiers,self.effects,self.energies)

    def test_highest_configured_tier_and_all_slots_use_maximum_requirement(self):
        p=self.plan()
        self.assertEqual((p['score_after'],p['tier_id']),(1200,3))
        self.assertEqual(p['energy_updates'],[dict(element=1,address=0x1000,before=10,after=30),dict(element=2,address=0x2000,before=40,after=40)])
        self.assertEqual(p['effect_count'],3)

    def test_existing_higher_score_and_energy_are_not_reduced(self):
        self.assertEqual(self.plan(1800)['score_after'],1800)
        self.assertEqual(self.plan()['energy_updates'][1]['after'],40)

    def test_unsorted_tiers_still_select_highest_threshold(self):
        self.tiers.reverse()
        self.assertEqual(self.plan()['tier_id'],3)

    def test_missing_element_refuses_instead_of_allocating_dictionary_entry(self):
        del self.energies[2]
        with self.assertRaises(Refused):self.plan()

    def test_duplicate_tier_id_or_score_threshold_refuses(self):
        for row in (dict(tier_id=1,score_min=500),dict(tier_id=9,score_min=600)):
            self.tiers.append(row)
            with self.assertRaises(Refused):self.plan()
            self.tiers.pop()

    def test_invalid_config_threshold_pool_state_and_address_refuse(self):
        for field,value in (('element',0),('element',6),('pool_id',0),('required',-1),('required',1000001),('activated',1)):
            with self.subTest(field=field,value=value):
                previous=self.effects[0][field];self.effects[0][field]=value
                with self.assertRaises(Refused):self.plan()
                self.effects[0][field]=previous
        for value in (0,True,0x1001):
            self.energies[1]['address']=value
            with self.assertRaises(Refused):self.plan()

    def test_score_bool_float_negative_and_over_limit_refuse(self):
        for value in (True,1.0,-1,1000001):
            with self.assertRaises(Refused):self.plan(value)

    def test_no_effect_prototype_needs_no_energy_mutation(self):
        self.effects=[];self.energies={}
        self.assertEqual(self.plan()['energy_updates'],[])

    def test_planning_never_changes_supplied_config_or_current_affixes(self):
        before=deepcopy((self.tiers,self.effects,self.energies))
        self.plan()
        self.assertEqual(before,(self.tiers,self.effects,self.energies))


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter=CraftingAdapter.__new__(CraftingAdapter)
        self.adapter.blocked=False
        self.shown=dict(can_complete=True,identity=('one',),reason='',effect_count=3,highest_tier=4,
                        native=dict(plan={'score_after':900},effects=[1],energy={'version':5},tiers=[1],placement={'score_before':-1}))
        self.adapter.snapshot=Mock(return_value=deepcopy(self.shown))
        self.pending=patch('crafting_adapter.native_calls_pending',return_value=False).start()
        self.addCleanup(patch.stopall)

    def test_same_round_and_board_prepares(self):
        self.assertEqual(self.adapter.prepare_solve(self.shown),self.shown)

    def test_changed_round_and_each_mutable_board_component_refuse(self):
        fresh=self.adapter.snapshot.return_value
        fresh['identity']=('two',)
        with self.assertRaises(Refused):self.adapter.prepare_solve(self.shown)
        for field in ('plan','effects','energy','tiers','placement'):
            fresh=deepcopy(self.shown);fresh['native'][field]=None
            self.adapter.snapshot.return_value=fresh
            with self.assertRaises(Refused):self.adapter.prepare_solve(self.shown)

    def test_pending_and_inactive_never_prepare(self):
        self.pending.return_value=True
        with self.assertRaises(Refused):self.adapter.prepare_solve(self.shown)
        self.adapter.snapshot.assert_not_called()
        self.pending.return_value=False
        self.adapter.snapshot.return_value=dict(can_complete=False,reason='inactive')
        with self.assertRaises(Refused):self.adapter.prepare_solve(self.shown)

    def test_native_started_does_not_claim_reward_or_save_verified(self):
        result=self.adapter.verify_native(dict(settlement_started=True,all_effects_activated=True,effect_count=3,tier_id=4),self.shown)
        self.assertTrue(result['verified']);self.assertFalse(result['settlement_verified'])
        self.assertIn('结果页',result['message'])

    def test_incomplete_native_outcome_is_uncertain(self):
        good=dict(settlement_started=True,all_effects_activated=True,effect_count=3,tier_id=4)
        for field in good:
            result=dict(good);result.pop(field)
            with self.assertRaises(UncertainWrite):self.adapter.verify_native(result,self.shown)

    def test_uncertain_solve_blocks_adapter(self):
        self.adapter.native=Mock();self.adapter.native.solve.side_effect=UncertainWrite('partial')
        with self.assertRaises(UncertainWrite):self.adapter.solve(self.shown)
        self.assertTrue(self.adapter.blocked)


class PlacementStateTests(unittest.TestCase):
    def setUp(self):
        self.resolver=CraftingResolver.__new__(CraftingResolver)
        self.pointers={'_pendingSessionCoroutine':0,'_prewarmCoroutine':0,'_pendingSettlement':0x4000,
                       'ClearedCells':0x5000,'AddedCells':0x6000,'_items':0x7000}
        self.values={(0x4000,'ScoreBefore'):-1,(0x4000,'ScoreAfter'):-1,(0x4000,'ElementType'):0,
                     (0x5000,'_size'):0,(0x6000,'_size'):0,(0x5000,'_version'):8,(0x6000,'_version'):4}
        self.resolver.boolean=Mock(return_value=False)
        self.resolver.pointer_field=Mock(side_effect=lambda obj,c,name,*a,**kw:self.pointers[name])
        self.resolver.integer=Mock(side_effect=lambda obj,c,name:self.values[obj,name])
        def obj(address,kind):
            if not address:raise Refused('missing object')
            return {'name':kind}
        self.resolver.obj=Mock(side_effect=obj)

    def state(self):return self.resolver.placement_state(0x1000,{})

    def test_reusable_empty_settlement_and_reset_prewarm_are_ready(self):
        result=self.state()
        self.assertEqual(result['address'],'0x4000')
        self.assertFalse(result['prewarm_complete'])
        self.assertEqual((result['score_before'],result['score_after']),(-1,-1))

    def test_successful_prewarm_also_allowed_with_no_pending_work(self):
        self.resolver.boolean.return_value=True
        self.assertTrue(self.state()['prewarm_complete'])

    def test_startup_coroutines_refuse(self):
        for name in ('_pendingSessionCoroutine','_prewarmCoroutine'):
            self.pointers[name]=0x8000
            with self.assertRaises(Refused):self.state()
            self.pointers[name]=0

    def test_pending_or_invalid_cell_counts_refuse(self):
        for address in (0x5000,0x6000):
            for count in (-1,1):
                self.values[address,'_size']=count
                with self.assertRaises(Refused):self.state()
            self.values[address,'_size']=0

    def test_even_one_unconsumed_score_refuses(self):
        for name in ('ScoreBefore','ScoreAfter'):
            self.values[0x4000,name]=0
            with self.assertRaises(Refused):self.state()
            self.values[0x4000,name]=-1

    def test_consumed_element_may_remain_but_invalid_element_refuses(self):
        self.values[0x4000,'ElementType']=5
        self.assertEqual(self.state()['element'],5)
        for value in (-1,6):
            self.values[0x4000,'ElementType']=value
            with self.assertRaises(Refused):self.state()

    def test_missing_persistent_data_or_collections_refuse(self):
        for name in ('_pendingSettlement','ClearedCells','AddedCells'):
            previous=self.pointers[name];self.pointers[name]=0
            with self.assertRaises(Refused):self.state()
            self.pointers[name]=previous


class ConfigContainerTests(unittest.TestCase):
    def setUp(self):
        self.r=CraftingResolver.__new__(CraftingResolver)
        self.r.obj=Mock(side_effect=lambda address,kind:{'klass':hex(0x2000 if address==0x1000 else 0x4000),'name':'Row[]'})
        self.r.info=Mock(return_value={})
        memory={0x2058:0x3000,0x4040:0x5000,0x6018:2,0x6020:0x7000,0x6028:0x8000}
        self.memory=memory
        self.r.q=Mock(side_effect=lambda address,**kw:memory[address])
        self.r.integer=Mock(side_effect=lambda obj,c,name:2 if name=='_size' else 8)
        self.r.pointer_field=Mock(return_value=0x6000)

    def test_notifiable_container_uses_verified_parent_and_element_type(self):
        self.assertEqual(self.r.config_objects(0x1000,'LubanDatas.AlchemyScoreTierEntry'),(0x7000,0x8000))
        self.r.obj.assert_any_call(0x1000,'Emei.NotifiableList`1')
        self.r.info.assert_any_call(0x3000,'System.Collections.Generic.List`1')
        self.r.info.assert_any_call(0x5000,'LubanDatas.AlchemyScoreTierEntry')
        self.r.integer.assert_any_call(0x1000,{},'_version')

    def test_overflow_capacity_refuses(self):
        self.memory[0x6018]=65
        with self.assertRaises(Refused):self.r.config_objects(0x1000,'Row')

    def test_duplicate_configuration_objects_refuse(self):
        self.memory[0x6028]=0x7000
        with self.assertRaises(Refused):self.r.config_objects(0x1000,'Row')

    def test_parent_type_mismatch_refuses(self):
        self.r.info.side_effect=Refused('wrong parent')
        with self.assertRaises(Refused):self.r.config_objects(0x1000,'Row')


class NotifiableMetadataTests(unittest.TestCase):
    def setUp(self):
        self.r=CraftingResolver.__new__(CraftingResolver);self.r.meta=0x100000
        self.spec=SPECS['classes']['Emei.NotifiableList`1']
        self.c=dict(namespace='Emei',name='NotifiableList`1',fields=[dict(name=f['name'],token=hex(f['token'])) for f in self.spec['fields']])
        self.memory={0x2068:0,0x2060:0x3000,0x3000:0x4000,0x3018:0x2000}
        self.r.q=Mock(side_effect=lambda address,**kw:self.memory[address])
        self.r.i=Mock(return_value=self.spec['token'])
        raw=(self.r.meta+self.spec['type_definition_offset']).to_bytes(8,'little')+b'\0\0\x12'+b'\0'*5
        self.r.anchor=Mock(return_value=raw)
        patcher=patch('crafting_adapter.LearningResolver.info',return_value=self.c)
        patcher.start();self.addCleanup(patcher.stop)

    def test_inflated_generic_definition_resolves_to_reviewed_metadata(self):
        self.assertIs(self.r.info(0x2000,'Emei.NotifiableList`1'),self.c)

    def test_cached_generic_class_must_match(self):
        self.memory[0x3018]=0x9000
        with self.assertRaises(Refused):self.r.info(0x2000)

    def test_wrong_generic_definition_rejected(self):
        self.r.anchor.return_value=b'\0'*16
        with self.assertRaises(Refused):self.r.info(0x2000)

    def test_same_named_unreviewed_metadata_rejected(self):
        self.memory[0x2068]=self.r.meta+self.spec['type_definition_offset']+88
        with self.assertRaises(Refused):self.r.info(0x2000)


if __name__=='__main__':unittest.main()
