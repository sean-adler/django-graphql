from django.test import TestCase
from django.utils import timezone

from models import Container
from models import Item
from models import ItemInContainer
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
            ItemInContainer.objects.create(
                item=items[i],
                container=containers[0])
            for i in range(5)
        ]

        throughs[-1].left = timezone.now()
        throughs[-1].save()

        ItemInContainer.objects.create(
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
