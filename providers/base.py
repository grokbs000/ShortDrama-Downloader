from abc import ABC, abstractmethod

class Provider(ABC):
    name = "base"

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        return False

    def search(self, keyword: str):
        raise NotImplementedError

    def get_drama(self, drama_id: str):
        raise NotImplementedError

    def get_episodes(self, drama_id: str):
        raise NotImplementedError

    def resolve_episode(self, episode):
        raise NotImplementedError
