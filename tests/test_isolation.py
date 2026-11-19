import ipaddress
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from frost.isolation import check_capacity, MIB
from frost.spawner import Manager


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.fs = SimpleNamespace(f_frsize=4096, f_blocks=16*MIB,
                                  f_bavail=10*MIB, f_files=300000, f_favail=140000)

    def admit(self, available=10*1024, players=0, resident=None, policy="reserved"):
        memory = f"MemTotal: 16777216 kB\nMemAvailable: {available*1024} kB\n"
        with patch("frost.isolation.Path.read_text", return_value=memory), \
             patch("frost.isolation.os.statvfs", return_value=self.fs):
            check_capacity("/", players, resident, policy)

    def test_capacity_with_headroom(self):
        self.admit(players=24)

    def test_ram_available_and_committed(self):
        with self.assertRaisesRegex(ValueError, "RAM"):
            self.admit(available=2100)
        with self.assertRaisesRegex(ValueError, "RAM"):
            self.admit(players=56)
        with self.assertRaisesRegex(ValueError, "RAM"):
            self.admit(available=7*1024, players=22)

    def test_16_gib_vm_with_3_gib_in_use(self):
        # The former check rejected 48 running slots with 13 GiB available.
        used = Mock(return_value=48*32*MIB)
        self.admit(available=13*1024, players=48, resident=used)
        used.assert_called_once()
        with self.assertRaisesRegex(ValueError, "13312 von 16384 MiB"):
            self.admit(available=13*1024, players=48, resident=lambda:0)

    def test_host_meminfo_precedes_container_view(self):
        from frost.isolation import host_memory
        def read(path):
            total = 16*1024 if path.name=="frost-host-meminfo" else 512
            return f"MemTotal: {total*1024} kB\nMemAvailable: {total*512} kB\n"
        with patch("frost.isolation.Path.read_text", autospec=True, side_effect=read):
            self.assertEqual(host_memory(), (16384*MIB,8192*MIB))

    def test_available_policy_keeps_real_reserve_and_disk_checks(self):
        unused=Mock(side_effect=AssertionError("unnecessary stats call"))
        self.admit(available=13*1024, players=70, resident=unused, policy="available")
        with self.assertRaisesRegex(ValueError, "RAM"):
            self.admit(available=2303, players=70, resident=unused, policy="available")
        self.fs.f_bavail=1024
        with self.assertRaisesRegex(ValueError, "Speicherplatz"):
            self.admit(players=70, policy="available")

    def test_archive_space_for_online_players(self):
        self.fs.f_bavail = 5*1024*MIB//4096
        self.admit(players=2)
        with self.assertRaisesRegex(ValueError, "Speicherplatz"):
            self.admit(players=8)

    def test_inode_reserve(self):
        self.fs.f_favail = 8000
        with self.assertRaisesRegex(ValueError, "Speicherplatz"):
            self.admit()


class SpawnerLimitsTests(unittest.TestCase):
    def test_network_allocation_skips_occupied_blocks(self):
        docker = Mock()
        docker.call.return_value = [{"IPAM": {"Config": [{"Subnet": cidr}]}}
                                    for cidr in ["10.0.0.0/28", "10.0.0.16/30", "fd00::/64"]]
        manager = SimpleNamespace(docker=docker, pool=ipaddress.ip_network("10.0.0.0/24"))
        Manager.allocate_network(manager, "slot", {})
        spec = docker.call.call_args.args[2]
        self.assertEqual(spec["IPAM"]["Config"][0]["Subnet"], "10.0.0.24/29")
        self.assertTrue(spec["Internal"])

    def test_admission_before_any_player_resources_are_created(self):
        with patch("frost.spawner.time.monotonic", return_value=0):
            manager = SimpleNamespace(lock=threading.RLock(), paused=False, credit_at=0,
                                      join_credit=1, admit=Mock(side_effect=ValueError("reserve")))
            with self.assertRaisesRegex(ValueError, "reserve"):
                Manager.create(manager)
            self.assertEqual(manager.join_credit, 1)
            manager.join_credit = 0
            with self.assertRaisesRegex(ValueError, "Anmeldungen"):
                Manager.create(manager)
            manager.admit.assert_called_once()

    def test_admission_credits_only_resident_anonymous_memory(self):
        docker=Mock()
        rows=[{"Id":ident,"Image":"frostbyte:local","Labels":{"frost.managed":"shell-game"}}
              for ident in ("one","two","three")]
        rows.extend([
            {"Id":"direct","Image":"sha256:old","Labels":{"com.docker.compose.service":"player01",
                                                          "com.docker.compose.project":"shell-game"}},
            {"Id":"unrelated","Image":"other","Labels":{"com.docker.compose.service":"player01",
                                                        "com.docker.compose.project":"other"}},
        ])
        def call(method,path):
            if path=="/containers/json": return rows
            if "/one/" in path: stats={"anon":20*MIB,"file":110*MIB}
            elif "/two/" in path: stats={"total_rss":18*MIB,"rss":17*MIB}
            else: stats={}
            return {"memory_stats":{"usage":190*MIB,"stats":stats}}
        docker.call.side_effect=call
        manager=SimpleNamespace(docker=docker,config={"image":"frostbyte:local","project":"shell-game"})
        with patch("frost.spawner.check_capacity") as check:
            Manager.admit(manager)
            root,count,credit,policy=check.call_args.args
            self.assertEqual((root,count),("/run/controller",4))
            self.assertEqual(credit(),38*MIB)

    def test_full_join_queue_rejects_immediately(self):
        manager = SimpleNamespace(join_queue=threading.BoundedSemaphore(1), create=Mock())
        manager.join_queue.acquire()
        with self.assertRaisesRegex(ValueError, "Anmeldungen"):
            Manager.new_join(manager)
        manager.create.assert_not_called()
