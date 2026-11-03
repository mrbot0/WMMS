"""Tests for the server's behaviour when the browser goes away and under many parallel requests."""
import http.client
import io
import sys
import threading
import unittest
from unittest import mock

from tests import test_api
from wmm.server import api


class Disconnects(unittest.TestCase):
    def test_server_ignores_closed_connections(self):
        server = api.AgentServer.__new__(api.AgentServer)
        errori = io.StringIO()
        for errore in (ConnectionAbortedError(), ConnectionResetError(), BrokenPipeError()):
            try:
                raise errore
            except OSError:
                with mock.patch.object(sys, "stderr", errori):
                    server.handle_error(None, ("127.0.0.1", 1))
        self.assertEqual(errori.getvalue(), "")

    def test_other_errors_still_reach_the_log(self):
        server = api.AgentServer.__new__(api.AgentServer)
        errori = io.StringIO()
        try:
            raise ValueError("real bug")
        except ValueError:
            with mock.patch.object(sys, "stderr", errori):
                server.handle_error(None, ("127.0.0.1", 1))
        self.assertIn("real bug", errori.getvalue())


class Parallel(unittest.TestCase):
    setUp = test_api.ApiTests.setUp
    tearDown = test_api.ApiTests.tearDown
    admin = True

    def test_many_parallel_requests_all_answer(self):
        risultati = []

        def chiedi():
            connessione = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
            connessione.request("GET", "/api/v1/agent/info")
            risultati.append(connessione.getresponse().status)
            connessione.close()

        fili = [threading.Thread(target=chiedi) for _ in range(40)]
        for filo in fili:
            filo.start()
        for filo in fili:
            filo.join(30)
        self.assertEqual(risultati, [200] * 40)

    def test_handler_answers_a_failing_route_with_json(self):
        with mock.patch.object(self.agent, "info", side_effect=RuntimeError("boom")):
            connessione = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
            connessione.request("GET", "/api/v1/agent/info")
            risposta = connessione.getresponse()
            self.assertEqual(risposta.status, 500)
            self.assertIn(b"boom", risposta.read())
            connessione.close()

    def test_store_uses_write_ahead_log(self):
        with self.agent.store._db() as db:
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")


if __name__ == "__main__":
    unittest.main()
