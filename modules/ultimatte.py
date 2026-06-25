import logging
import socket

logger = logging.getLogger(__name__)

class Ultimatte():
    enabled = True
    
    def __init__(self, enable, host, port):
        self.host = host
        self.port = port
        
        if not enable:
            Ultimatte.enabled = False

    def send(self, action: str) -> int:
        """Send messages to Ultimatte over socket connection.
        
        This will open a new socket connection to the Ultimatte
        over ethernet. It will send either of two messages
        depending on action. Then it will wait for a response and
        close the connection after it received this.

        This function will return:
        0 if no message has been sent
        1 if a message has been sent but not received
        2 if a message has been sent and received

        Keep in mind that this function blocks the main thread.
        """
        result: int = 0

        if not Ultimatte.enabled:
            return 2

        match action:
            case "key-off":
                msg = "CONTROL:\nMonitor Out: fg\n\n"
            case "key-on":
                msg = "CONTROL:\nMonitor Out: program\n\n"
            case _:
                logger.error(f"Ultimatte: unknown action : {action}")
                return 0

        # Try block to capture connect, DNS or socket open errors
        try:
            # "with" will automatically close the connection
            with socket.create_connection(
                (self.host, self.port), timeout=5
            ) as s:
                s.settimeout(5)
                s.sendall(msg.encode("utf-8"))
                logger.info(f"Ultimatte : sending message : {msg}")
                result = 1
      
                # Try block to capture timeouts
                try:
                    received = s.recv(1024).decode("utf-8", errors="replace")

                    if received:
                        result = 2
                        logger.info("Ultimatte : received response")

                except socket.timeout:
                    logger.error("Ultimatte : did not receive a reply")

                except Exception:
                    logger.exception(
                        "Ultimatte : unexpected error while receiving"
                    )

        except (OSError, socket.error) as e:
            logger.error(f"Ultimatte : socket error : {e}")
            return 0
        
        logger.info("Ultimatte : connection closed")
        return result