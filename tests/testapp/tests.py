from django.test import TestCase
from django.utils import timezone

from django_graphql.lib import DjangoSchema
from django_graphql.sql_debug import DjangoDebugPlugin

from models import Container
from models import Item
from models import ItemMovement
from schema import schema


class GraphQLExecutionTests(TestCase):
    def setUp(self):
        containers = [
            Container.objects.create(name='container_%s' % i)
            for i in range(2)
        ]

        items = [
            Item.objects.create(name='item_%s' % i)
            for i in range(5)
        ]

        throughs = [
            ItemMovement.objects.create(
                item=items[i],
                container=containers[0])
            for i in range(5)
        ]

        throughs[-1].left = timezone.now()
        throughs[-1].save()

        ItemMovement.objects.create(
            item=items[-1],
            container=containers[1])


    def test_item_request(self):
        result = schema.execute("""
            {
              item(name: "item_4") {
                id
                name
                containers {
                  id
                  name
                  items {
                    id
                    name
                  }
                }
              }
            }
        """)

        self.assertEqual(result.errors, [])
        self.assertDictEqual(
            result.data, {
            'item':
                {
                    'id': 5,
                    'name': 'item_4',
                    'containers': [
                        {
                            'id': 1,
                            'name': 'container_0',
                            'items': [
                                {
                                    'id': 1,
                                    'name': 'item_0'
                                },
                                {
                                    'id': 2,
                                    'name': 'item_1'
                                },
                                {
                                    'id': 3,
                                    'name': 'item_2'
                                },
                                {
                                    'id': 4,
                                    'name': 'item_3'
                                },
                                {
                                    'id': 5,
                                    'name': 'item_4'
                                }
                            ]
                        },
                        {
                            'id': 2,
                            'name': 'container_1',
                            'items': [
                                {
                                    'id': 5,
                                    'name': 'item_4'
                                }
                            ]
                        }
                    ]
                }
        })


    def test_container_request(self):
        result = schema.execute("""
        {
            container(id: 1) {
                id,
                name,
                items {
                    id,
                    name,
                    current_container {
                        id,
                        name
                    }
                }
                current_items {
                    id,
                    name
                }
            }
        }
        """)

        self.assertDictEqual(
            result.data, {
            'container': {
                'id': 1,
                'name': 'container_0',
                'items': [
                    {
                        'id': 1,
                        'name': 'item_0',
                        'current_container': {
                            'id': 1,
                            'name': 'container_0'
                        }
                    },
                    {
                        'id': 2,
                        'name': 'item_1',
                        'current_container': {
                            'id': 1,
                            'name': 'container_0'
                        }
                    },
                    {
                        'id': 3,
                        'name': 'item_2',
                        'current_container': {
                            'id': 1,
                            'name': 'container_0'
                        }
                    },
                    {
                        'id': 4,
                        'name': 'item_3',
                        'current_container': {
                            'id': 1,
                            'name': 'container_0'
                        }
                    },
                    {
                        'id': 5,
                        'name': 'item_4',
                        'current_container': {
                            'id': 2,
                            'name': 'container_1'
                        }
                    }
                ],
                'current_items': [
                    {
                        'id': 1,
                        'name': 'item_0'
                    },
                    {
                        'id': 2,
                        'name': 'item_1'
                    },
                    {
                        'id': 3,
                        'name': 'item_2'
                    },
                    {
                        'id': 4,
                        'name': 'item_3'
                    }
                ]
            }
        })

    def test_filters(self):
        pass

    def test_prefetch(self):
        pass

    def test_debug_sql(self):
        """
        Tests that `DjangoDebugPlugin` properly instruments SQL queries
        executed by GraphQL schema.
        """
        # Add DjangoDebug plugin without mutating original schema.
        sql_debug_schema = DjangoSchema(schema.registry, [DjangoDebugPlugin()])
        result = sql_debug_schema.execute("""
            {
              item(name: "item_4") {
                id,
                name,
                containers {
                  id,
                  name,
                  items {
                    id,
                    name
                  }
                }
              },
              __debug {
                query_count,
                queries {
                  sql,
                }
              }
            }
        """)

        self.assertDictEqual(
            result.data,
            {
                '__debug': {
                    'query_count': 4,
                    'queries': [
                        {
                            'sql': (
                                'QUERY = u\'SELECT (1) AS "a" FROM "testapp_item" '
                                'WHERE "testapp_item"."name" = %s '
                                'LIMIT 1\' - PARAMS = (u"\'item_4\'",)'
                            )
                        },
                        {
                            'sql': (
                                'QUERY = u\'SELECT "testapp_item"."id", '
                                '"testapp_item"."name" FROM "testapp_item" '
                                'WHERE "testapp_item"."name" = %s '
                                'LIMIT 1\' - PARAMS = (u"\'item_4\'",)'
                            )
                        },
                        {
                            'sql': (
                                'QUERY = u\'SELECT ("testapp_itemmovement"."item_id") '
                                'AS "_prefetch_related_val_item_id", "testapp_container"."id", '
                                '"testapp_container"."name" '
                                'FROM "testapp_container" '
                                'INNER JOIN "testapp_itemmovement" '
                                'ON ( "testapp_container"."id" = "testapp_itemmovement"."container_id" ) '
                                'WHERE "testapp_itemmovement"."item_id" IN (%s)\' - PARAMS = (u\'5\',)'
                            )
                        },
                        {

                            'sql': (
                                'QUERY = u\'SELECT ("testapp_itemmovement"."container_id") '
                                'AS "_prefetch_related_val_container_id", "testapp_item"."id", '
                                '"testapp_item"."name" '
                                'FROM "testapp_item" '
                                'INNER JOIN "testapp_itemmovement" '
                                'ON ( "testapp_item"."id" = "testapp_itemmovement"."item_id" ) '
                                'WHERE "testapp_itemmovement"."container_id" IN (%s, %s)\' - PARAMS = (u\'1\', u\'2\')'
                            )
                        }
                    ]
                },
            'item': {
                 'containers': [
                    {
                        'id': 1,
                        'name': 'container_0',
                        'items': [
                            {
                                'id': 1,
                                'name': 'item_0'
                            },
                            {
                                'id': 2,
                                'name': 'item_1'
                            },
                            {
                                'id': 3,
                                'name': 'item_2'
                            },
                            {
                                'id': 4,
                                'name': 'item_3'
                            },
                            {
                                'id': 5,
                                'name': 'item_4'
                            }
                        ],
                    },
                    {
                        'id': 2,
                        'name': 'container_1',
                        'items': [
                            {
                                'id': 5,
                                'name': 'item_4'
                            }
                        ]
                    }
                ],
                'id': 5,
                'name': 'item_4'
            }
        })
