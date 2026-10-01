import copy
import struct
import unittest
from unittest.mock import Mock

from alchemy_recipe import AlchemyRecipeAdapter, isolated_recipes
from write_guard import Refused, UncertainWrite


def poi(ident, kind=2, tier=1, x=100, y=100, string_index=0):
    return struct.pack('<iBBHiiiiiii', ident, kind, 0, tier, 0, string_index, x, y, 0, 0, 0)


class CandidateTests(unittest.TestCase):
    def test_nearest_allowed_independent_recipe(self):
        raw=poi(1,x=900)+poi(2,x=120)+poi(3,kind=6,x=500)+poi(4,tier=5,x=110)
        result=isolated_recipes(raw,(100,100),5,2)
        self.assertEqual([p['poi_id'] for p in result],[2,1])

    def test_overlapping_any_poi_excluded_even_exact_radius(self):
        for kind in (1,2,3,4,5,6):
            with self.subTest(kind=kind):
                raw=poi(1)+poi(2,kind=kind,x=150)+poi(3,x=700)
                self.assertEqual([p['poi_id'] for p in isolated_recipes(raw,(100,100),50,1)],[3])

    def test_all_overlapping_returns_empty(self):
        self.assertEqual(isolated_recipes(poi(1)+poi(2,kind=6),(100,100),50,5),[])

    def test_invalid_raw_and_bounds_refused(self):
        for raw,pos,radius,furnace in ((b'',(0,0),1,1),(b'x',(0,0),1,1),
            (poi(1),(float('nan'),0),1,1),(poi(1),(0,0),0,1),(poi(1),(0,0),float('inf'),1),
            (poi(1),(0,0),1,0),(poi(1),(0,0),1,6),(poi(0),(0,0),1,1),
            (poi(1)+poi(1,x=200),(0,0),1,1),(poi(1,x=-1),(0,0),1,1)):
            with self.subTest(raw=raw),self.assertRaises(Refused):
                isolated_recipes(raw,pos,radius,furnace)


class LifecycleTests(unittest.TestCase):
    def adapter(self):
        a=AlchemyRecipeAdapter.__new__(AlchemyRecipeAdapter)
        a.blocked=False;a.native=Mock();a.resolver=Mock(_selected_methods={})
        a.resolver.method.return_value='0x100';a.resolver.proof.return_value=['proof']
        s=dict(can_solve=True,identity=(11,22,33),candidate=dict(recipe_id=1000002,name='回元散'),
               native=dict(panel_class='0x200',move_class='0x300'))
        a.snapshot=Mock(return_value=copy.deepcopy(s))
        return a,s

    def test_prepare_re_resolves_candidate_and_three_methods(self):
        a,s=self.adapter();fresh=a.prepare_solve(s)
        self.assertEqual(set(fresh['native']['methods']),{'teleport','collect','available'})
        self.assertEqual(a.resolver.method.call_count,3)

    def test_inactive_or_new_round_or_new_target_is_not_authorized(self):
        for field,value in [('can_solve',False),('identity',(2,3)),('candidate',dict(recipe_id=1000001))]:
            a,s=self.adapter();a.snapshot.return_value[field]=value
            with self.subTest(field=field),self.assertRaises(Refused):a.prepare_solve(s)
            a.resolver.method.assert_not_called()

    def test_missing_shown_cannot_dispatch(self):
        for shown in (None,{},dict(can_solve=False)):
            a,_=self.adapter()
            with self.assertRaises(Refused):a.prepare_solve(shown)
            a.snapshot.assert_not_called()

    def test_postcondition_requires_matching_current_recipe(self):
        a,s=self.adapter()
        for out in ({},dict(recipe_collected=True,recipe_id=1),dict(recipe_id=1000002,recipe_collected=False)):
            with self.assertRaises(UncertainWrite):a.verify_native(out,s)
        self.assertTrue(a.verify_native(dict(recipe_collected=True,recipe_id=1000002),s)['verified'])

    def test_uncertain_blocks_adapter(self):
        a,s=self.adapter();a.native.solve.side_effect=UncertainWrite('unknown')
        with self.assertRaises(UncertainWrite):a.solve(s)
        self.assertTrue(a.blocked)


if __name__=='__main__':unittest.main()
