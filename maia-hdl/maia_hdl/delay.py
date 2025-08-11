from amaranth import *
from amaranth.sim import Simulator, Tick
from amaranth.lib.memory import Memory

class BRAMDelay(Elaboratable):
    """
    BRAM-based circular delay line using amaranth.lib.memory.Memory.
    """
    def __init__(self, width : int, depth : int, delay : int, clk_domain : str):
        assert 0 <= delay < depth
        self.width  = width
        self.shape = width * 2
        self.depth  = depth
        self.delay  = delay
        self.clk_domain = clk_domain

        self.re_in = Signal(width)
        self.im_in = Signal(width)
        self.write_en = Signal()
        self.re_out = Signal(width)
        self.im_out = Signal(width)
        self.read_en = Signal()

    def elaborate(self, platform):
        m = Module()

        m.submodules.mem = mem = Memory(
            shape=self.shape, depth=self.depth, init=[])

        wr = mem.write_port(domain=self.clk_domain)
        rd = mem.read_port(domain=self.clk_domain)

        addr_bits = (self.depth - 1).bit_length()
        write_ptr = Signal(addr_bits)

        # write logic
        m.d.comb += [
            wr.addr.eq(write_ptr),
            wr.data.eq(Cat(self.re_in, self.im_in)),
            wr.en.eq(self.write_en),
        ]
        with m.If(self.write_en):
            m.d.sync += write_ptr.eq(write_ptr + 1)

        # read pointer
        read_addr = Signal(addr_bits)
        if (self.depth & (self.depth - 1)) == 0:
            mask = self.depth - 1
            m.d.comb += read_addr.eq((write_ptr - self.delay) & mask)
        else:
            with m.If(write_ptr >= self.delay):
                m.d.comb += read_addr.eq(write_ptr - self.delay)
            with m.Else():
                m.d.comb += read_addr.eq(write_ptr + (self.depth - self.delay))

        m.d.sync += rd.addr.eq(read_addr)

        m.d.sync += [
            self.re_out.eq(rd.data[:self.width]),
            self.im_out.eq(rd.data[self.width:]),
            rd.en.eq(self.read_en),
        ]

        return m


def run_testbench(width=36, depth=1024, delay=5, total_cycles=4096):
    dut = BRAMDelay(width=width, depth=depth, delay=delay)
    sim = Simulator(dut)
    sim.add_clock(1e-6)

    bram_read_latency = 1
    DO_reg = 1
    effective_delay = delay + bram_read_latency + DO_reg

    def process():
        written_values = []
        mismatches = 0

        for cycle in range(total_cycles):
            val = cycle & ((1 << width) - 1)
            yield dut.data_in.eq(val)
            yield dut.write_en.eq(1)
            yield Tick()

            written_values.append(val)
            out = (yield dut.data_out)

            idx = cycle - effective_delay
            if idx >= 0:
                expected = written_values[idx]
                if out != expected:
                    print(f"[MIS] cycle={cycle} out={out} expected={expected}")
                    mismatches += 1

        print("SIM DONE:", mismatches, "mismatches")
        if mismatches == 0:
            print("TEST PASSED")

    sim.add_testbench(process)
    with sim.write_vcd("bram_delay.vcd", "bram_delay.gtkw", traces=[]):
        sim.run()


if __name__ == "__main__":
    run_testbench()
