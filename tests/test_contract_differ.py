import unittest

from src.contract_differ import ContractDiffEngine


class TestContractDiffEngine(unittest.TestCase):

    def setUp(self):

        self.official_spec = {
            "openapi": "3.0.0",
            "info": {
                "title": "Official API",
                "version": "1.0.0",
            },
            "paths": {
                "/api/v1/users": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "Success"
                            }
                        }
                    }
                },
                "/api/v1/orders/{id}": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "Success"
                            }
                        }
                    }
                },
            },
        }

        self.live_spec = {
            "openapi": "3.0.0",
            "info": {
                "title": "Live API",
                "version": "1.0.0",
            },
            "paths": {
                "/api/v1/users": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "Success"
                            }
                        }
                    }
                },
                "/api/v1/admin/users": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "Success"
                            }
                        }
                    }
                },
            },
        }

    def test_extract_routes(self):

        engine = ContractDiffEngine(
            self.official_spec,
            self.live_spec,
        )

        routes = engine._extract_routes(
            self.official_spec
        )

        self.assertIn(
            ("GET", "/api/v1/users"),
            routes,
        )

        self.assertIn(
            ("GET", "/api/v1/orders/{id}"),
            routes,
        )

    def test_common_route_is_detected(self):

        engine = ContractDiffEngine(
            self.official_spec,
            self.live_spec,
        )

        result = engine.diff_routes()

        self.assertIn(
            {
                "method": "GET",
                "path": "/api/v1/users",
            },
            result["common"],
        )

    def test_live_only_route_is_detected(self):

        engine = ContractDiffEngine(
            self.official_spec,
            self.live_spec,
        )

        result = engine.diff_routes()

        self.assertIn(
            {
                "method": "GET",
                "path": "/api/v1/admin/users",
            },
            result["live_only"],
        )

    def test_official_only_route_is_detected(self):

        engine = ContractDiffEngine(
            self.official_spec,
            self.live_spec,
        )

        result = engine.diff_routes()

        self.assertIn(
            {
                "method": "GET",
                "path": "/api/v1/orders/{id}",
            },
            result["official_only"],
        )

    def test_deprecated_live_route_is_zombie(self):

        official_spec = {
            "openapi": "3.0.0",
            "info": {
                "title": "Official API",
                "version": "1.0.0",
            },
            "paths": {
                "/api/v1/legacy": {
                    "get": {
                        "deprecated": True,
                        "responses": {
                            "200": {
                                "description": "Success"
                            }
                        }
                    }
                }
            },
        }

        live_spec = {
            "openapi": "3.0.0",
            "info": {
                "title": "Live API",
                "version": "1.0.0",
            },
            "paths": {
                "/api/v1/legacy": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "Success"
                            }
                        }
                    }
                }
            },
        }

        engine = ContractDiffEngine(
            official_spec,
            live_spec,
        )

        result = engine.diff_routes()

        self.assertIn(
            {
                "method": "GET",
                "path": "/api/v1/legacy",
                "status": "ZOMBIE_API",
            },
            result["zombie"],
        )

    def test_summary_counts_are_correct(self):

        engine = ContractDiffEngine(
            self.official_spec,
            self.live_spec,
        )

        result = engine.diff()

        self.assertEqual(
            result["summary"]["official_routes"],
            2,
        )

        self.assertEqual(
            result["summary"]["live_routes"],
            2,
        )

        self.assertEqual(
            result["summary"]["common"],
            1,
        )

        self.assertEqual(
            result["summary"]["live_only"],
            1,
        )

        self.assertEqual(
            result["summary"]["official_only"],
            1,
        )

    def test_empty_live_spec(self):

        engine = ContractDiffEngine(
            self.official_spec,
            {
                "paths": {}
            },
        )

        result = engine.diff()

        self.assertEqual(
            result["summary"]["live_routes"],
            0,
        )

        self.assertEqual(
            result["summary"]["official_only"],
            2,
        )

    def test_empty_official_spec(self):

        engine = ContractDiffEngine(
            {
                "paths": {}
            },
            self.live_spec,
        )

        result = engine.diff()

        self.assertEqual(
            result["summary"]["official_routes"],
            0,
        )

        self.assertEqual(
            result["summary"]["live_only"],
            2,
        )

    def test_invalid_paths_are_ignored(self):

        official_spec = {
            "paths": "invalid"
        }

        live_spec = {
            "paths": {
                "/users": {
                    "get": {}
                }
            }
        }

        engine = ContractDiffEngine(
            official_spec,
            live_spec,
        )

        result = engine.diff()

        self.assertEqual(
            result["summary"]["official_routes"],
            0,
        )

        self.assertEqual(
            result["summary"]["live_routes"],
            1,
        )

    def test_non_http_path_fields_are_ignored(self):

        spec = {
            "paths": {
                "/users": {
                    "get": {},
                    "parameters": [],
                    "summary": "Users API",
                }
            }
        }

        engine = ContractDiffEngine(
            spec,
            {"paths": {}},
        )

        routes = engine._extract_routes(spec)

        self.assertEqual(
            routes,
            {
                ("GET", "/users")
            },
        )


if __name__ == "__main__":
    unittest.main()