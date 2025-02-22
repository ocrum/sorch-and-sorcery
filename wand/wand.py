from networking import Networking
from machine import Pin, SoftI2C, ADC, PWM
import asyncio
from lsm6ds3 import LSM6DS3
from button import Button

class Spell:
    """
    Enum-like class representing spell types. This includes the 4 spells directions (UP, DOWN, LEFT, RIGHT) and a type
    to represent unrecognized spells.
    """
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    OTHER = "other"

class Wand:
    """
    Class used for a wand device equipped with motion sensors and a button. It uses an accelerometer/gyroscope sensor
    (LSM6DS3) to detect wand movement and determine which "spell" was cast (up, down, left, right). The determined spell
    is then broadcast over an ESPNOW-like network to another device.
    """
    def __init__(self):
        self.tag_state = False     # whether tagged
        self.msg = ""               # Last message from the network

        # Initialize I2C
        self.i2c = SoftI2C(scl=Pin(23), sda=Pin(22)) # 23 -> Pin 5; 22 -> Pin 4
        self.lsm = LSM6DS3(self.i2c)

        self.button = Button(pin_num=0)

        # Networking
        self.networking = Networking()

    def my_callback(self):
        """
        Check for any incoming messages from the network and update self.msg with the latest message.
        """
        for mac, message, rtime in self.networking.aen.return_messages(): #You can directly iterate over the function
            self.msg = message

    def read_movement_data(self):
        """
        Reads the sensor data from the LSM6DS3 device and returns the up down and left right rotational data
        Adjust these axes as needed based on the wand orientation.

        Returns:
            (float, float): (left right rotation data, up down rotation data)
        """
        ax, ay, az, gx, gy, gz = self.lsm.get_readings()
        return gy, gx

    def determine_spell(self, lr_data, ud_data):
        """
        Given collected lateral (lr_data) and up/down (ud_data) motion readings from the wand,
        determine which spell direction was cast.

        The method counts the number of samples above or below a threshold to guess
        a direction. If no direction surpasses the threshold, it attempts to find a
        direction with the highest absolute value movement, otherwise it's classified as OTHER.

        Args:
            lr_data (list): A list of gyroscope/acceleration samples corresponding to left/right motion.
            ud_data (list): A list of gyroscope/acceleration samples corresponding to up/down motion.

        Returns:
            str: One of the Spell constants (UP, DOWN, LEFT, RIGHT, OTHER).
        """
        THRESHOLD = 32764

        counts = {
            Spell.UP: (sum(1 for value in ud_data if value >= THRESHOLD), abs(max(ud_data, default=0))),
            Spell.DOWN: (sum(1 for value in ud_data if value <= -THRESHOLD), abs(min(ud_data, default=0))),
            Spell.LEFT: (sum(1 for value in lr_data if value >= THRESHOLD), abs(max(lr_data, default=0))),
            Spell.RIGHT: (sum(1 for value in lr_data if value <= -THRESHOLD), abs(min(lr_data, default=0)))
        }

        max_spell, (max_count, _) = max(counts.items(), key=lambda x: x[1][0])
        max_weak_spell, (_, max_weak_val) = max(counts.items(), key=lambda x: x[1][1])
        if max_count == 0:
            print(max_weak_val)
        return max_spell if max_count > 0 else (max_weak_spell if max_weak_val > 10 else Spell.OTHER)

    async def puzzle(self):
        """
        This asynchronous method waits until the button is pressed, then records wand movement data
        during the entire pressing period. After the button is released, it attempts to determine
        the spell movement and send it as a message over the network.

        The button press acts as a "trigger" to start collecting motion data. When the user releases
        the button, the collected data is analyzed to find a movement direction.
        """
        if self.button.is_pressed():
            lr_data = []
            ud_data = []
            while self.button.is_being_pressed():
                await asyncio.sleep_ms(10)
                gz, gx = self.read_movement_data()
                lr_data.append(gz)
                ud_data.append(gx)

            movement = self.determine_spell(lr_data, ud_data)

            if movement == Spell.OTHER:
                print("other spell")
            else:
                print(movement)
                self.networking.aen.send(b'\xFF\xFF\xFF\xFF\xFF\xFF', b'!' + movement)
                await asyncio.sleep_ms(10)  # TODO Tune the cooldown as needed

    async def run(self):
        """
        Main loop for the wand. Continuously checks for incoming network messages and
        simultaneously listens for button presses to detect spells. Uses asyncio.gather
        to run multiple asynchronous tasks.
        """
        while True:
            self.my_callback()
            await asyncio.gather(
                self.puzzle(),
            )

# Initialize the Wand object and run the tasks asynchronously
wand = Wand()
asyncio.run(wand.run())