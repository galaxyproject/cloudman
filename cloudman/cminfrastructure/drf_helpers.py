from abc import ABCMeta, abstractmethod

from django.core.urlresolvers import NoReverseMatch
from django.http.response import Http404
from rest_framework import mixins
from rest_framework import relations
from rest_framework import viewsets
from rest_framework.response import Response

from cminfrastructure import util


# ==================================
# Django Rest Framework View Helpers
# ==================================
class CustomNonModelObjectMixin(object):
    """
    A custom viewset mixin to make it easier to work with non-django-model viewsets.
    Only the list_objects() and retrieve_object() methods need to be implemented.
    Create and update methods will work normally through DRF's serializers.
    """
    __metaclass__ = ABCMeta

    def get_queryset(self):
        return self.list_objects()

    def get_object(self):
        obj = self.retrieve_object()
        if obj is None:
            raise Http404

        # May raise a permission denied
        self.check_object_permissions(self.request, obj)
        return obj

    @abstractmethod
    def list_objects(self):
        """
        Override this method to return the list of objects for
        list() methods.
        """
        pass

    @abstractmethod
    def retrieve_object(self):
        """
        Override this method to return the object for the get method.
        If the returned object is None, an HTTP404 will be raised.
        """
        pass


class CustomModelViewSet(CustomNonModelObjectMixin, viewsets.ModelViewSet):
    pass


class CustomReadOnlyModelViewSet(CustomNonModelObjectMixin,
                                 viewsets.ReadOnlyModelViewSet):
    pass


class CustomReadOnlySingleViewSet(CustomNonModelObjectMixin,
                                  mixins.ListModelMixin,
                                  viewsets.GenericViewSet):

    def list(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def get_object(self):
        # return an empty data row so that the serializer can emit fields
        return {}

# ===========================================
# Django Rest Framework Serialization Helpers
# ===========================================


class CustomHyperlinkedRelatedField(relations.HyperlinkedRelatedField):
    """
    This custom hyperlink field builds up the arguments required to link to a
    nested view of arbitrary depth, provided the ``parent_url_kwargs`` parameter
    is passed in. This parameter must contain a list of ``kwarg`` names that are
    required for django's ``reverse()`` to work. The values for each argument
    are obtained from the serializer context. It's modelled after drf-nested-
    routers' ``NestedHyperlinkedRelatedField``.
    """
    lookup_field = 'pk'

    def __init__(self, *args, **kwargs):
        self.parent_url_kwargs = kwargs.pop('parent_url_kwargs', [])
        super(CustomHyperlinkedRelatedField, self).__init__(*args, **kwargs)

    def get_url(self, obj, view_name, request, format):
        """
        Given an object, return the URL that hyperlinks to the object.
        May raise a ``NoReverseMatch`` if the ``view_name`` and ``lookup_field``
        attributes are not configured to correctly match the URL conf.
        """
        # Unsaved objects will not yet have a valid URL.
        if hasattr(obj, 'pk') and obj.pk is None:
            return None

        reverse_kwargs = {}
        # Use kwargs from view if available. When using the serializer
        # manually, a view may not be available. If so, the required
        # args must be supplied through the serializer context
        if 'view' in self.context:
            reverse_kwargs = {key: val for key, val in self.context['view'].kwargs.items()
                              if key in self.parent_url_kwargs}
        # Let serializer context values override view kwargs
        reverse_kwargs.update({key: val for key, val in self.context.items()
                               if key in self.parent_url_kwargs})
        if self.lookup_field:
            lookup_value = util.getattrd(obj, self.lookup_field)
            if lookup_value:
                reverse_kwargs.update({self.lookup_url_kwarg: lookup_value})
        try:
            return self.reverse(
                view_name, kwargs=reverse_kwargs, request=request, format=format)
        except NoReverseMatch as e:
            # If the reverse() failed when the lookup_value is empty, just
            # ignore, since it's probably a null value in the dataset
            if self.lookup_field and lookup_value:
                raise e
            return ""


class CustomHyperlinkedIdentityField(CustomHyperlinkedRelatedField):
    """
    A version of the ``CustomHyperlinkedRelatedField`` dedicated to creating
    identity links. It's simply copied from rest framework's
    ``relations.HyperlinkedRelatedField``.
    """
    lookup_field = 'pk'

    def __init__(self, *args, **kwargs):
        kwargs['read_only'] = True
        # The asterisk is a special value that DRF has an interpretation
        # for: It will result in the source being set to the current object.
        # itself. (Usually, the source is a field of the current object being
        # serialized)
        kwargs['source'] = '*'
        super(CustomHyperlinkedIdentityField, self).__init__(*args, **kwargs)


