"""Coordinate one memory scalar write with every GUI sharing the native host.

No host is started and no Frida module is imported here. A startup mutex closes
the no-host/host-start race; an existing host supplies a mutually exclusive
scalar lease. The original writer performs all validation after this wait.
"""
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from functools import wraps

import native_broker as broker
from runtime_paths import SAFETY_LOG_ROOT
from write_guard import Refused, UncertainWrite


@dataclass
class ScalarLease:
    possible_write: bool = False
    uncertain: bool = False


@contextmanager
def scalar_write_guard(identity, *, epoch_path=None):
    identity = broker._identity(identity)
    epoch = epoch_path if epoch_path is not None else SAFETY_LOG_ROOT / "acquisition-native-epochs.json"
    endpoint = broker.endpoint_path(identity, epoch)
    lease = ScalarLease()
    with ExitStack() as locks:
        try:
            locks.enter_context(broker.startup_lock(endpoint))
        except Refused:
            raise
        except Exception as error:
            raise Refused("无法取得数值修改协调锁，未写入。") from error
        proxy = None
        claimed = False
        try:
            try:
                descriptor = broker.read_endpoint(endpoint, identity)
                if descriptor is not None:
                    proxy = broker._connect_existing(descriptor)
                    if proxy is None:
                        raise Refused("原生后台已经退出，无法核对操作状态；未修改数值。")
                    answer = proxy.call("claim_scalar", timeout=3)
                    if not isinstance(answer, dict) or answer.get("claimed") is not True:
                        raise Refused("原生后台未确认数值修改所有权，未写入。")
                    claimed = True
            except Refused:
                raise
            except Exception as error:
                raise Refused("无法核对原生后台状态，未修改数值。") from error
            # Old standalone epochs without a host retain their existing
            # scalar-edit behavior; no epoch is deleted or reinterpreted.
            try:
                yield lease
            except UncertainWrite:
                lease.possible_write = lease.uncertain = True
                raise
            except Refused:
                raise
            except BaseException:
                # A Win32 exception may come from a partially completed WPM.
                # Preserve the original exception for the caller's journal,
                # but never tell the host that this was a known safe outcome.
                lease.possible_write = lease.uncertain = True
                raise
            finally:
                if claimed:
                    try:
                        answer = proxy.call("release_scalar", {"uncertain": lease.uncertain}, timeout=3)
                        acknowledged = (isinstance(answer, dict) and
                            (answer.get("released") is True and not lease.uncertain or
                             lease.uncertain and answer.get("released") is False and answer.get("uncertain") is True))
                        if not acknowledged:
                            raise Refused("原生后台没有确认结束数值修改。")
                    except Exception as error:
                        if lease.possible_write:
                            raise UncertainWrite("数值写入后的后台状态未确认，请核对游戏，勿重复操作。") from error
                        raise Refused("数值尚未写入，但后台协调状态未确认；请保留日志后检查。") from error
        finally:
            if proxy is not None:
                try:
                    proxy.close_transport()
                except Exception:
                    pass


def coordinated_scalar_write(method):
    """Wrap the entire low-level validation/write, never just the OS call."""
    @wraps(method)
    def guarded(self, *args, **kwargs):
        try:
            identity = (self.reader.pid, self.stamp[1])
        except (AttributeError, IndexError, TypeError) as error:
            raise Refused("数值修改缺少有效的游戏进程身份。") from error
        with scalar_write_guard(identity) as lease:
            result = method(self, *args, **kwargs)
            lease.possible_write = True
            return result
    guarded._scalar_coordinated = True
    return guarded
