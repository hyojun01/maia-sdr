#
# Copyright (C) 2022-2024 Daniel Estevez <daniel@destevez.net>
#
# This file is part of maia-sdr
#
# SPDX-License-Identifier: MIT
#

from amaranth import *
import amaranth.back.verilog
from amaranth.lib.cdc import FFSynchronizer, PulseSynchronizer

from .fifo import AsyncFifo18_36

class TxDUMP(Elaboratable):
    """
    Parameters
    ----------
    i_domain : str
        Input clock domain.
    o_domain : str
        Output clock domain.
    width : int
        Data width.

    Attributes
    ----------
    re_in : Signal(width), in
        Input real part.
    im_in : Signal(width), in
        Input imaginary part.
    reset : Signal(), in
        FIFO reset. This signal is assumed to be asynchronous with respect to
        the i_domain clock, so it can be driven by the o_domain clock.
    strobe_out : Signal(), out
        Output strobe out. It is asserted when a new sample is presented in
        the output.
    re_out : Signal(width), out
        Output real part.
    im_out : Signal(width), out
        Output imaginary part.
    """
    def __init__(self, i_domain: str, o_domain: str, width: int):
        self._i_domain = i_domain
        self._o_domain = o_domain
        self.w = width
        if self.w > 18:
            raise ValueError('width > 18 not supported')

        # i_domain
        self.re_in = Signal(width)
        self.im_in = Signal(width)
        self.valid_re = Signal()
        self.valid_im = Signal()

        # o_domain
        self.reset = Signal()
        self.re_out = Signal(width)
        self.im_out = Signal(width)

    def elaborate(self, platform):
        m = Module()
        m.submodules.fifo = fifo = AsyncFifo18_36(
            r_domain=self._o_domain, w_domain=self._i_domain)

        # i_domain

        # o_domain -> i_domain reset
        #
        # This synchronizer already provides sufficient delay between the time
        # that the FIFO sees the deassertion of reset and the first time that
        # wren is asserted.
        reset_i = Signal()
        m.submodules.sync_reset = FFSynchronizer(
            self.reset, reset_i, o_domain=self._i_domain, init=1)

        m.d.comb += [
            fifo.data_in.eq(Cat(self.re_in, self.im_in)),
            fifo.wren.eq(~reset_i),
        ]

        # o_domain
        m.d.comb += [
            self.re_out.eq(fifo.data_out[:self.w]),
            self.im_out.eq(fifo.data_out[self.w:]),
            fifo.rden.eq(self.valid_re & self.valid_im & ~fifo.empty),
            fifo.reset.eq(self.reset),
        ]

        return m
    
def gen_verilog_txdump():
    m = Module()
    internal = ClockDomain()
    m.domains += internal
    m.submodules.dump = dump = TxDUMP('sync', 'internal', 18)
    with open('tx_dump.v', 'w') as f:
        f.write(amaranth.back.verilog.convert(
            m, ports=[
                dump.re_in, dump.im_in, dump.reset, dump.valid_re, dump.valid_im,
                dump.re_out, dump.im_out, internal.clk, internal.rst,
            ],
            emit_src=False))
        
if __name__ == '__main__':
    gen_verilog_txdump()