"""Offline regressions: never call models, matching, stores or production APIs."""
import copy
import json
import unittest
from unittest.mock import patch
import app as B


class IntentDisplayGuard(unittest.TestCase):
    def test_display_aliases(self):
        for word in ('movie', 'movies', 'film', 'cinema'):
            for lang, title in [('ru', 'Поговорить про кино'), ('es', 'Hablar de películas')]:
                with self.subTest(word=word, lang=lang):
                    topics = [word]
                    self.assertEqual(B._title_for(topics, [], 'social', lang, 'discuss')[0], title)
                    self.assertEqual(topics, [word])

    def test_unknown_subject_not_replaced_by_known_secondary(self):
        self.assertIn('labubu', B._title_for(['labubu', 'music'], [], 'social', 'ru', 'discuss')[0].lower())
        self.assertEqual(B._title_for(['coffee'], [], 'social', 'ru', 'discuss')[0], 'Поговорить про кофе')

    def test_builder_block_before_any_generation(self):
        messages = [{'role': 'user', 'content': 'test blocked request'}]
        with patch.object(B.safety, 'check_conversation', return_value=('block', 'test')), \
             patch.object(B, 'llm_complete', side_effect=AssertionError('must not generate')), \
             patch.object(B, 'llm_stream', side_effect=AssertionError('must not stream')):
            result = B.intent_build(messages, {}, lang='ru')
        self.assertFalse(result['ready'])
        self.assertIsNone(result['intent'])
        self.assertEqual(result['refused'], 'test')

    def test_refusal_overrules_model_flags(self):
        for lang, refusal in B.REFUSE_REPLY.items():
            with self.subTest(lang=lang), \
                 patch.object(B.safety, 'check_conversation', return_value=('care', 'test')), \
                 patch.object(B, 'llm_complete', return_value=json.dumps({'reply':refusal,'valid':True,'ready':True,'match':True,'activity':'coffee','signals':{}})), \
                 patch.object(B, '_categorize', side_effect=AssertionError('no intent categorization')):
                messages = [{'role':'user','content':{'ru':'У меня есть вопрос','en':'I have a question','es':'Tengo una pregunta'}[lang]}]
                before = copy.deepcopy(messages)
                for result in [B.intent_build(messages, {}, lang=lang), B.buddy_chat(messages, {}, {}, lang=lang)]:
                    self.assertIsNone(result['intent'])
                    self.assertTrue(result['refused'])
                self.assertEqual(messages, before)

    def test_ordinary_reply_not_refusal(self):
        for text in ['Давай поговорим про кино.', 'We can discuss recovery and support.', 'Podemos hablar de prevención.', 'Не буду спойлерить фильм.']:
            self.assertFalse(B._reply_refuses(text), text)

    def test_streamed_refusal_keeps_intent_empty(self):
        refusal = B.REFUSE_REPLY['ru']
        emitted = []
        def stream(*args, **kwargs):
            args[4](refusal)
            return json.dumps({'reply':refusal,'valid':True,'ready':True,'match':True,'activity':'coffee'})
        with patch.object(B.safety, 'check_conversation', return_value=('care','test')), \
             patch.object(B,'llm_stream', side_effect=stream), \
             patch.object(B,'_categorize', side_effect=AssertionError('no categorization')):
            for fn in [lambda: B.intent_build([{'role':'user','content':'У меня вопрос'}],{},on_text=emitted.append,lang='ru'),
                       lambda: B.buddy_chat([{'role':'user','content':'У меня вопрос'}],{},{},on_text=emitted.append,lang='ru')]:
                result=fn()
                self.assertIsNone(result['intent'])
                self.assertTrue(result['refused'])
        self.assertTrue(emitted)

    def test_safe_discussion_is_not_blanket_blocked(self):
        # Same sensitive domain, but policy says this is a permissible discussion.
        with patch.object(B.safety,'check_conversation',return_value=('care','test')), \
             patch.object(B,'llm_complete',return_value=json.dumps({'reply':'Какую сторону темы обсудим?','valid':True,'ready':False,'activity':'coffee'})), \
             patch.object(B,'_categorize',return_value={'topics':['coffee']}), \
             patch.object(B,'_teach'):
            result=B.intent_build([{'role':'user','content':'Хочу обсудить поддержку и профилактику'}],{},lang='ru')
        self.assertFalse(result.get('refused'))
        self.assertTrue(result['valid'])

    def test_display_does_not_change_machine_fields(self):
        cat={'topics':['movie'],'category':'culture','role':'discuss'}
        ru=B.build_intent({},cat,'movie','ru')
        en=B.build_intent({},cat,'movie','en')
        self.assertEqual(ru['topics'],en['topics'])
        self.assertEqual(ru['tags'],en['tags'])
        self.assertEqual(ru['title'],'Поговорить про кино')


if __name__ == '__main__':
    unittest.main()
