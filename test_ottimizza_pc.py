"""Test delle parti che non toccano il sistema: python -m unittest -v"""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import ottimizza_pc as op


class LetturaServizi(unittest.TestCase):
    def test_tipi_di_avvio(self):
        casi = {
            "START_TYPE         : 2   AUTO_START": "auto",
            "START_TYPE         : 2   AUTO_START  (DELAYED)": "delayed-auto",
            "START_TYPE         : 3   DEMAND_START": "demand",
            "START_TYPE         : 4   DISABLED": "disabled",
        }
        for testo, atteso in casi.items():
            self.assertEqual(op.leggi_avvio_servizio(testo), atteso)

    def test_servizio_assente(self):
        self.assertIsNone(op.leggi_avvio_servizio("[SC] OpenService FAILED 1060"))

    def test_stato_attivo(self):
        self.assertTrue(op.servizio_attivo("STATE              : 4  RUNNING"))
        self.assertFalse(op.servizio_attivo("STATE              : 1  STOPPED"))


class ListeServizi(unittest.TestCase):
    def test_nessun_servizio_protetto_nelle_liste(self):
        gestiti = set(op.SERVIZI_SICURI + op.SERVIZI_MANUALI + op.SERVIZI_XBOX + op.SERVIZI_STAMPA)
        self.assertFalse(gestiti & op.SERVIZI_PROTETTI)


class BackupServizi(unittest.TestCase):
    def setUp(self):
        self.cartella = tempfile.TemporaryDirectory()
        radice = Path(self.cartella.name)
        for attributo, valore in (("DATI", radice), ("REGISTRO", radice / "r.txt"), ("BACKUP_SERVIZI", radice / "b.json")):
            patch = mock.patch.object(op, attributo, valore)
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(self.cartella.cleanup)
        self.ctx = op.Contesto()

    def _finto_sc(self, modo="2   AUTO_START"):
        def leggi(comando):
            return f"START_TYPE : {modo}" if comando[1] == "qc" else "STATE : 4 RUNNING"
        return leggi

    def test_servizio_protetto_rifiutato(self):
        with self.assertRaises(ValueError):
            op.imposta_servizi(op.Contesto(anteprima=True), ["WinDefend"], "disabled")

    def test_backup_prima_della_modifica_e_conserva_originale(self):
        ordine = []

        def finto_run(comando, **_):
            ordine.append((comando[1], op.BACKUP_SERVIZI.exists()))
            return mock.Mock(returncode=0)

        with mock.patch.object(self.ctx, "leggi", self._finto_sc()), mock.patch.object(op.subprocess, "run", finto_run):
            op.imposta_servizi(self.ctx, ["SysMain"], "disabled")
        self.assertEqual(ordine, [("stop", True), ("config", True)])
        self.assertEqual(op.leggi_backup()["SysMain"], {"avvio": "auto", "attivo": True})

        with mock.patch.object(self.ctx, "leggi", self._finto_sc("3   DEMAND_START")), mock.patch.object(op.subprocess, "run", finto_run):
            op.imposta_servizi(self.ctx, ["SysMain"], "disabled")
        self.assertEqual(op.leggi_backup()["SysMain"]["avvio"], "auto")

    def test_ripristino_rimuove_solo_i_riusciti(self):
        op.scrivi_backup({"A": {"avvio": "auto", "attivo": True}, "B": {"avvio": "demand", "attivo": False}})
        comandi = []

        def finto_run(comando, **_):
            comandi.append(comando)
            return mock.Mock(returncode=1 if comando[2] == "B" else 0)

        with mock.patch.object(op.subprocess, "run", finto_run):
            esito = op.ripristina_servizi(self.ctx)
        self.assertEqual(esito.stato, op.Stato.AVVISO)
        self.assertIn(["sc", "start", "A"], comandi)
        self.assertEqual(list(op.leggi_backup()), ["B"])

    def test_anteprima_non_modifica(self):
        ctx = op.Contesto(anteprima=True)
        with mock.patch.object(ctx, "leggi", self._finto_sc()), mock.patch.object(op.subprocess, "run") as finto:
            op.imposta_servizi(ctx, ["SysMain"], "disabled")
        finto.assert_not_called()
        self.assertFalse(op.BACKUP_SERVIZI.exists())


class Selezione(unittest.TestCase):
    ids = list(range(1, 28))

    def test_ordine_intervalli_doppioni(self):
        self.assertEqual(op.leggi_selezione("6 2,10-12 2", self.ids), [6, 2, 10, 11, 12])

    def test_intervallo_inverso(self):
        self.assertEqual(op.leggi_selezione("12-10", self.ids), [12, 11, 10])

    def test_errori(self):
        for testo in ("", "99", "abc"):
            with self.assertRaises(ValueError):
                op.leggi_selezione(testo, self.ids)


class Sequenze(unittest.TestCase):
    def test_punto_ripristino_sempre_primo_se_si_modifica(self):
        self.assertEqual(op.prepara_sequenza([6, 15])[0], [1, 6, 15])
        self.assertEqual(op.prepara_sequenza([6, 1, 15])[0], [1, 6, 15])

    def test_ogni_sequenza_ha_la_sua_lettera(self):
        self.assertEqual(sorted(op.LETTERE_SEQUENZE.values()), sorted(op.SEQUENZE))

    def test_sola_lettura_senza_punto(self):
        self.assertEqual(op.prepara_sequenza([2, 3])[0], [2, 3])

    def test_avvisi(self):
        self.assertTrue(op.prepara_sequenza([11, 10])[1])
        self.assertTrue(op.prepara_sequenza([24, 25])[1])

    def test_sequenze_valide_e_senza_passi_rischiosi(self):
        for _, ids in op.SEQUENZE.values():
            self.assertTrue(all(i in op.PER_ID for i in ids))
            self.assertFalse([i for i in ids if op.PER_ID[i].conferma])

    def test_errore_non_ferma_la_sequenza(self):
        ctx = mock.Mock(riavvio_necessario=False, anteprima=True)
        guasto = op.Passo(101, "x", "guasto", mock.Mock(side_effect=RuntimeError("no")), modifica=False)
        buono = op.Passo(102, "x", "buono", mock.Mock(return_value=op.Esito(op.Stato.OK)), modifica=False)
        with mock.patch.dict(op.PER_ID, {101: guasto, 102: buono}):
            risultati = op.esegui_sequenza(ctx, [101, 102])
        self.assertEqual([r[1].stato for r in risultati], [op.Stato.ERRORE, op.Stato.OK])

    def test_blocco_di_sicurezza_ferma_i_successivi(self):
        ctx = mock.Mock(riavvio_necessario=False, anteprima=True)
        blocco = op.Passo(101, "x", "blocco", mock.Mock(side_effect=op.SequenzaFermata("no")), modifica=False)
        azione = mock.Mock(return_value=op.Esito(op.Stato.OK))
        dopo = op.Passo(102, "x", "dopo", azione, modifica=False)
        with mock.patch.dict(op.PER_ID, {101: blocco, 102: dopo}):
            risultati = op.esegui_sequenza(ctx, [101, 102])
        azione.assert_not_called()
        self.assertEqual(risultati[1][1].stato, op.Stato.SALTATO)


class Pulizia(unittest.TestCase):
    def test_solo_file_vecchi_ed_esclusi_rispettati(self):
        with tempfile.TemporaryDirectory() as cartella:
            radice = Path(cartella)
            (radice / "Claude").mkdir()
            vecchio, recente, escluso = radice / "vecchio.tmp", radice / "nuovo.tmp", radice / "Claude" / "x.tmp"
            for file in (vecchio, recente, escluso):
                file.write_text("x")
            passato = time.time() - 10 * 86400
            os.utime(vecchio, (passato, passato))
            os.utime(escluso, (passato, passato))
            limite = time.time() - 3 * 86400
            self.assertEqual([p for p, _ in op.file_da_pulire(cartella, limite)], [str(vecchio)])


class Problemi(unittest.TestCase):
    def test_dati_sani(self):
        dati = {
            "memoria": {"liberaGB": 20, "totaleGB": 32},
            "dischi": [{"nome": "A", "salute": "Healthy", "usura": 5, "erroriLettura": 0}],
            "volumi": [{"lettera": "C", "liberoGB": 200, "totaleGB": 465}],
            "stabilita": {"spegnimenti": 0, "whea": 0, "disco": 0},
            "sistema": {"etaBiosGiorni": 100},
            "sicurezza": {"defender": True, "firewallSpenti": False},
            "riavvioInSospeso": False,
        }
        self.assertEqual(op.trova_problemi(dati), [])

    def test_dati_con_problemi(self):
        dati = {
            "dischi": {"nome": "A", "salute": "Warning", "usura": 90, "erroriLettura": 3},
            "volumi": [{"lettera": "C", "liberoGB": 36, "totaleGB": 465}],
            "stabilita": {"spegnimenti": 6, "whea": 1, "disco": 2},
            "sicurezza": {"defender": False},
        }
        self.assertEqual(len(op.trova_problemi(dati)), 8)

    def test_dati_vuoti(self):
        self.assertEqual(op.trova_problemi({}), [])


class Ping(unittest.TestCase):
    def test_statistiche(self):
        self.assertEqual(op.statistiche_ping([10, 20, 10], 4), {"media": 13.3, "massimo": 20.0, "jitter": 10.0, "persi": 1.0})

    def test_nessuna_risposta(self):
        self.assertEqual(op.statistiche_ping([], 10)["persi"], 10)


class Formati(unittest.TestCase):
    def test_dimensione(self):
        self.assertEqual(op.dimensione(1536 * 1024 * 1024), "1.5 GB")

    def test_report_con_dati_parziali(self):
        self.assertIn("SISTEMA", op.righe_report({}))
        self.assertIsInstance(json.dumps(op.righe_report({})), str)


if __name__ == "__main__":
    unittest.main()
