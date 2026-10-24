from providers.base import Provider
from resolver.detector import inspect_url

class GenericProvider(Provider):
    name = "generic"

    def can_handle(self, url):
        return url.startswith(("http://","https://"))

    def resolve_episode(self, episode):
        return inspect_url(episode["page_url"], referer=episode["page_url"])
