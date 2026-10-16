# -*- coding: utf-8 -*-
"""Один класс сервера на все службы Kleal — с очередью подключений, которой хватает.

ЗАЧЕМ. `ThreadingHTTPServer` берёт `request_queue_size` из `socketserver` — а там стоит ПЯТЬ.
Пять — это сколько подключений ядро подержит, пока служба их принимает; шестое получает отказ, и
снаружи это выглядит как 502. Пока батарея ходит 24 работниками, а приложение — по одному
человеку, пятёрки хватало. На 60 000 зарегистрированных не хватит: всплеск в полсотни одновременных
входов даёт отказы на ровном месте, и виноватой будет выглядеть модель.

Сто двадцать восемь — столько же, сколько по умолчанию держит nginx перед нами (`listen backlog`),
так что узкое место перестаёт быть у нас и становится общим для всей цепочки.
"""
from http.server import ThreadingHTTPServer


class KlealServer(ThreadingHTTPServer):
    request_queue_size = 128
    # Порт освобождается сразу: при выкладке служба перезапускается, и ждать TIME_WAIT нечего.
    allow_reuse_address = True

    def __init__(self, *args, age_gate_service=None, **kwargs):
        self.age_gate_service = age_gate_service
        super().__init__(*args, **kwargs)

    def finish_request(self, request, client_address):
        import age_verification_http as age_http
        original = self.RequestHandlerClass

        class Guarded(original):
            def handle_one_request(self):
                # HTTP keep-alive reuses a handler, not its configuration proof.
                import age_proof
                with age_proof.request_scope():
                    return super().handle_one_request()

            def log_message(self, *args):
                # Provider callback query strings must never enter access logs.
                if not age_http.path_of(self).startswith(age_http.age.PREFIX + '/'):
                    return super().log_message(*args)

            def end_headers(self):
                if (age_http.path_of(self).startswith(age_http.age.PREFIX + '/')
                        and age_http.path_of(self) != age_http.age.PREFIX + '/callback'):
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Referrer-Policy', 'no-referrer')
                    self.send_header('X-Content-Type-Options', 'nosniff')
                super().end_headers()

            def parse_request(self):
                if not super().parse_request():
                    return False
                if age_http.handle(self) or age_http.gate(self):
                    return False
                return True  # retain current production identity/authorization

        Guarded(request, client_address, self)
