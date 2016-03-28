## django-graphql
(WIP) Simple GraphQL bindings for Django models

### 3 steps to eternal happiness
1. Declare serializer classes
2. Instantiate a schema
3. Pass GraphQL strings to the schema

### Example

##### Example Models
Say we're modeling items moving through different containers. Each item can be in at most one container, and each container can hold zero or more items.

(See the [testapp](https://github.com/sean-adler/django-graphql/blob/master/tests/testapp/models.py))

```
class ItemInContainer(models.Model):
    entered = models.DateTimeField(default=timezone.now)
    left = models.DateTimeField(null=True, blank=True)
    item = models.ForeignKey('Item')
    container = models.ForeignKey('Container')


class Item(models.Model):
    name = models.CharField(max_length=100)


class Container(models.Model):
    name = models.CharField(max_length=100, unique=True)
    items = models.ManyToManyField(
        Item,
        through=ItemInContainer,
        related_name='containers')
```

##### Example Schema
Now that we've declared our Django models, we want to expose a JSON serialization layer. Typically we'll write one serializer class per model.

(See the [testapp](https://github.com/sean-adler/django-graphql/blob/master/tests/testapp/schema.py))

First we'll instantiate a `TypeRegistry` that holds the type mapping for our application.

```python
T = TypeRegistry()
```

Next, we'll actually declare our serializer classes, exposing whatever fields and behavior we care to have in our API layer.

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
```

Finally, we instantiate the schema that will accept GraphQL queries, passing it the registry that holds all our object types.

```python
schema = DjangoSchema(T)
```


##### Example Queries
After instantiating some items moving them into some containers, we can issue a GraphQL query for one of the items, crossing a relation and passing some nested fields.

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

### TODO
- [ ] Explain how `@prefetch` method decorator works
- [ ] SQL debugging example query
- [ ] Auto-generation of mutation root
