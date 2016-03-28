## django-graphql
(WIP) Simple GraphQL bindings for Django models


#### 3 steps to eternal happiness
1. Declare `DjangoType` classes for each Django model that you want to serialize
2. Create your schema
3. Pass GraphQL strings to `schema.execute()`

#### Example Schema
(See the [tests](https://github.com/sean-adler/django-graphql/blob/master/tests/testapp/schema.py))

```python
class Container(DjangoType):
    id = T.Int
    name = T.String
    items = [T.Item]
    current_items = [T.Item]

    def get_items(self, obj, args, info):
        return obj.items.all()

    def get_current_items(self, obj, args, info):
        return obj.items.filter(itemincontainer__left__isnull=True)

    class Meta:
        model = models.Container
        filters = (
            'id',
            'name'
        )


class Item(DjangoType):
    id = T.Int
    name = T.String
    containers = [T.Container]
    current_container = T.Container

    def get_containers(self, obj, args, info):
        return obj.containers.all()

    def get_current_container(self, obj, args, info):
        return obj.containers.get(itemincontainer__left__isnull=True)

    class Meta:
        model = models.Item
        filters = (
            'id',
            'name'
        )


schema = DjangoSchema(T)
```


#### Example Queries
(See the [tests](https://github.com/sean-adler/django-graphql/blob/master/tests/testapp/tests.py#L37-L53))

```python
query_string = """
    {
      item(name: "item_2") {
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
"""

schema.execute(query_string).data
>>> {
        'item':
            {
                'id': 3,
                'name': 'item_2',
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
                            }
                        ]
                    },
                    {
                        'id': 2,
                        'name': 'container_1',
                        'items': [
                            {
                                'id': 3,
                                'name': 'item_2'
                            }
                        ]
                    }
                ]
            }
      }
```

#### TODO
- [ ] Explain how `@prefetch` method decorator works
- [ ] SQL debugging example query
