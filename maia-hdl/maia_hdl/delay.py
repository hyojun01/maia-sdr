from amaranth import *
from amaranth.lib.memory import Memory
from amaranth.sim import Simulator, Tick

class BankedBRAM(Elaboratable):

    def __init__(self, bank_bits, width):
        self.row_bits   = 9                                 # 하나의 BRAM 내부 주소 비트
        self.bank_bits  = bank_bits                         # BRAM 개수에 따른 제어 비트
        self.addr_bits  = self.row_bits + self.bank_bits    # 전체 주소 비트
        self.num_banks = 1 << self.bank_bits                # BRAM 개수
        self.width = width                                  # BRAM 데이터 폭

        self.w_en   = Signal()                              # 쓰기 인에이블
        self.w_addr = Signal(self.addr_bits)                # 쓰기 주소
        self.w_data = Signal(self.width)                    # 쓰기 데이터

        self.r_en   = Signal()                              # 읽기 인에이블
        self.r_addr = Signal(self.addr_bits)                # 읽기 주소
        self.r_data = Signal(self.width)                    # 읽기 데이터

    def elaborate(self, platform):
        m = Module()

        bank_sel_w  = Signal(self.bank_bits)                # 쓰기 제어 비트
        row_w       = Signal(self.row_bits)                 # 쓰기 BRAM 내부 주소
        bank_sel_r  = Signal(self.bank_bits)                # 읽기 제어 비트
        row_r       = Signal(self.row_bits)                 # 읽기 BRAM 내부 주소

        m.d.comb += [
            bank_sel_w.eq(self.w_addr[self.row_bits:]),
            row_w.eq(self.w_addr[:self.row_bits]),
            bank_sel_r.eq(self.r_addr[self.row_bits:]),
            row_r.eq(self.r_addr[:self.row_bits]),
        ]

        # 여러 개의 BRAM 생성
        mems = [Memory(shape=self.width, depth=2**self.row_bits, init=[])
                for _ in range(self.num_banks)]
        for i, mem in enumerate(mems):
            setattr(m.submodules, f"mem_{i}", mem)
        
        rdports = [mem.read_port() for mem in mems]
        wrports = [mem.write_port() for mem in mems]

        # 각 BRAM의 읽기 및 쓰기 포트 연결
        for i in range(self.num_banks):
            cond_w = Signal()
            cond_r = Signal()

            m.d.comb += [
                cond_w.eq(self.w_en & (bank_sel_w == i)),   # 쓰기 인에이블 신호
                cond_r.eq(self.r_en & (bank_sel_r == i)),   # 읽기 인에이블 신호

                wrports[i].addr.eq(row_w),
                wrports[i].data.eq(self.w_data),
                wrports[i].en.eq(cond_w),

                rdports[i].addr.eq(row_r),
                rdports[i].en.eq(cond_r),
            ]

        rsel_q = [Signal(name=f'rsel{i}_q', reset_less=True)
                  for i in range(self.num_banks)]
        for i in range(self.num_banks):
            m.d.sync += rsel_q[i].eq(rdports[i].en)

        # 활성화된 BRAM 읽기 데이터 포트 연결
        for i in range(self.num_banks):
            with m.If(rsel_q[i]):
                m.d.comb += self.r_data.eq(rdports[i].data)

        return m
    
class BRAMDelay(Elaboratable):
    def __init__(self, bank_bits, width, delay):
        assert 0 < delay < (1 << bank_bits)*(2**9)
        self.row_bits   = 9
        self.bank_bits  = bank_bits
        self.addr_bits  = self.row_bits + self.bank_bits
        self.width = width
        self.offset = delay

        self.write_en   = Signal()
        self.in_data    = Signal(self.width)
        self.read_en    = Signal()
        self.out_data   = Signal(self.width)

    def elaborate(self, platform):
        m = Module()

        m.submodules.mem = mem = BankedBRAM(bank_bits=self.bank_bits,
                                            width=self.width)

        wptr = Signal(self.addr_bits)
        rptr = Signal(self.addr_bits)

        with m.If(self.write_en):
            m.d.sync += wptr.eq(wptr + 1)

        # 쓰기 포인터와 읽기 포인터의 오프셋
        m.d.comb += rptr.eq(wptr - self.offset)

        m.d.comb += [
            # RX 샘플이 주어지는 순간에 enable
            mem.w_en.eq(self.write_en),
            mem.w_addr.eq(wptr),
            mem.w_data.eq(self.in_data),

            mem.r_en.eq(self.read_en),
            mem.r_addr.eq(rptr),

            self.out_data.eq(mem.r_data),
        ]

        return m

def run_testbench(bank_bits=2, width=36, delay=10, total_cycles=1024*4):
    dut = BRAMDelay(bank_bits=bank_bits, width=width, delay=delay)
    sim = Simulator(dut)
    sim.add_clock(1e-6)

    bram_read_latency = 0
    DO_reg = 0
    effective_delay = delay + bram_read_latency + DO_reg

    def process():
        written_values = []
        mismatches = 0

        for cycle in range(total_cycles):
            val = cycle & ((1 << width) - 1)
            yield dut.in_data.eq(val)
            yield dut.write_en.eq(1)
            yield dut.read_en.eq(1)
            yield Tick()

            written_values.append(val)
            out = (yield dut.out_data)

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
    with sim.write_vcd("delay_new.vcd", "delay_new.gtkw", traces=[]):
        sim.run()


if __name__ == "__main__":
    run_testbench()