import unittest

from compose_network import choose


class NetworkTests(unittest.TestCase):
    def test_respects_docker_and_host_vpn_routes(self):
        self.assertEqual(
            choose(["10.200.0.0/24"], ["10.200.1.0/24", "192.168.1.0/24", "0.0.0.0/0"]),
            "10.200.2.0/24",
        )

    def test_rejects_overlapping_or_nonprivate_manual_choice(self):
        for choice in ["10.200.0.0/24", "8.8.8.0/24", "10.200.0.0/16"]:
            with self.assertRaises(ValueError):
                choose([], ["10.0.0.0/8"], choice)

    def test_missing_route_inventory_fails_closed(self):
        with self.assertRaises(ValueError):
            choose([], [])
