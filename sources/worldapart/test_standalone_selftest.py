"""Offline page coverage and scroll-aware packaging checks."""
from types import SimpleNamespace
import unittest

import standalone_selftest as st


class Widget:
    def __init__(self,kind,*children):
        self.kind,self.children = kind,children
    def winfo_children(self):return self.children
    def winfo_class(self):return self.kind


class ReleaseUiTests(unittest.TestCase):
    def test_eighteen_pages_required_with_interaction_assists(self):
        self.assertEqual(len(st.EXPECTED_TABS),18)
        for title in ('角色点数','背包数量','修行储备','增加寿元','当前资源','游戏速度','留影石','秒说服'):
            self.assertIn(title,st.EXPECTED_TABS)
        for old in ('角色与背包','当前精力'):
            self.assertNotIn(old,st.EXPECTED_TABS)

    def test_sidebar_routes_each_page_once_and_has_expected_group_order(self):
        st.validate_release_navigation(st.EXPECTED_NAVIGATION)
        self.assertEqual([name for pages in st.EXPECTED_NAVIGATION.values() for name in pages],
                         ['角色点数','人物属性','资质与技艺','修行储备','增加寿元','背包数量',
                          '添加物品与秘籍','当前资源','功法学习小游戏','疏经导脉辅助','游戏速度',
                          '留影石','秒说服','炼丹辅助','丹方探索','炼器辅助','双修','刮玉'])
        self.assertEqual({title for pages in st.EXPECTED_NAVIGATION.values() for title in pages},set(st.EXPECTED_TABS))
        for wrong in ({},dict(st.EXPECTED_NAVIGATION,游戏辅助=('游戏速度',)),
                      dict(reversed(list(st.EXPECTED_NAVIGATION.items())))):
            with self.subTest(wrong=wrong),self.assertRaises(RuntimeError):
                st.validate_release_navigation(wrong)

    def test_scroll_wrapper_does_not_hide_sibling_content_buttons(self):
        first,second = Widget('TButton'),Widget('Button')
        content = Widget('TFrame',first,Widget('TFrame',Widget('TLabel'),second))
        wrapper = Widget('TFrame',Widget('Canvas'),Widget('TScrollbar'))
        wrapper.content = content
        self.assertEqual(set(st.iter_page_buttons(wrapper)),{first,second})
        self.assertEqual(set(st.iter_page_buttons(content)),{first,second})

    def test_vertical_scroll_content_is_reachable_but_clipped_controls_fail(self):
        self.assertTrue(st.validate_button_geometry([30,850,100,30],[620,920],'scroll button'))
        for bounds,size in (([30,850,100,30],[860,730]),([600,20,100,30],[620,920]),
                            ([-1,10,100,30],[620,920]),([10,-1,100,30],[620,920])):
            with self.subTest(bounds=bounds,size=size),self.assertRaises(RuntimeError):
                st.validate_button_geometry(bounds,size,'clipped')

    def test_withdrawn_unknown_geometry_is_not_reported_verified(self):
        self.assertFalse(st.validate_button_geometry([0,0,1,1],[860,730],'not laid out'))


if __name__ == '__main__':unittest.main()
