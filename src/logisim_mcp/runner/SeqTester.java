// Headless sequential runner for Logisim Evolution 5.0.0.
//
// CircuitState is bound to this thread and Propagator runs synchronously,
// so Simulator and the Swing event thread are not involved. new Project()
// still starts a non-daemon PropagationThread; main always ends in
// System.exit so the process cannot hang on that thread.
//
// CLI:
//   SeqTester <circ> <circuit> <in0,in1,..> <out0,out1,..>
//   SeqTester --error-wires <circ> <circuit>
//
// An input named <tick> is not a pin. Its value is how many full clock
// cycles (toggleClocks + propagate, twice) to run after the other inputs
// are driven. Outputs may be Pins or LEDs, matched by label.
// stdin: one row per line, whitespace-separated values, inputs then outputs.

import com.cburch.logisim.circuit.Circuit;
import com.cburch.logisim.circuit.CircuitState;
import com.cburch.logisim.circuit.Propagator;
import com.cburch.logisim.circuit.Wire;
import com.cburch.logisim.comp.Component;
import com.cburch.logisim.data.AttributeSet;
import com.cburch.logisim.data.BitWidth;
import com.cburch.logisim.data.Value;
import com.cburch.logisim.file.Loader;
import com.cburch.logisim.file.LogisimFile;
import com.cburch.logisim.instance.InstanceState;
import com.cburch.logisim.instance.StdAttr;
import com.cburch.logisim.proj.Project;
import com.cburch.logisim.std.io.Led;
import com.cburch.logisim.std.wiring.Pin;

import java.io.BufferedReader;
import java.io.File;
import java.io.InputStreamReader;
import java.util.LinkedHashMap;
import java.util.Map;

public class SeqTester {

    static final String TICK = "<tick>";

    static final class QuietLoader extends Loader {
        QuietLoader() {
            super(null);
        }

        @Override
        public void showError(String description) {
            System.err.println(description);
        }
    }

    public static void main(String[] args) {
        int code = 1;
        try {
            code = run(args);
        } catch (Throwable thrown) {
            thrown.printStackTrace(System.err);
            code = 1;
        } finally {
            System.exit(code);
        }
    }

    static int run(String[] args) throws Exception {
        if (args.length >= 1 && "--error-wires".equals(args[0])) {
            if (args.length < 3) {
                System.err.println("usage: SeqTester --error-wires <circ> <circuit>");
                return 2;
            }
            Loaded loaded = open(args[1], args[2]);
            loaded.propagator.propagate();
            int errors = 0;
            for (Wire wire : loaded.circuit.getWires()) {
                Value a = loaded.state.getValue(wire.getEnd(0).getLocation());
                Value b = loaded.state.getValue(wire.getEnd(1).getLocation());
                if ((a != null && a.isErrorValue()) || (b != null && b.isErrorValue())) {
                    errors++;
                }
            }
            System.out.println("ERROR_WIRES=" + errors);
            return 0;
        }
        if (args.length < 4) {
            System.err.println(
                "usage: SeqTester <circ> <circuit> <in0,in1,..> <out0,out1,..>");
            return 2;
        }
        String[] inputs = args[2].isEmpty() ? new String[0] : args[2].split(",", -1);
        String[] outputs = args[3].isEmpty() ? new String[0] : args[3].split(",", -1);
        Loaded loaded = open(args[0], args[1]);
        Map<String, Component> pins = new LinkedHashMap<>();
        Map<String, Component> readable = new LinkedHashMap<>();
        for (Component comp : loaded.circuit.getNonWires()) {
            String label = labelOf(comp);
            if (label.isEmpty()) {
                continue;
            }
            if (comp.getFactory() instanceof Pin) {
                pins.put(label, comp);
                if (!isInputPin(comp)) {
                    readable.put(label, comp);
                }
            } else if (comp.getFactory() instanceof Led) {
                readable.put(label, comp);
            }
        }
        for (String name : inputs) {
            if (TICK.equals(name)) {
                continue;
            }
            Component pin = pins.get(name);
            if (pin == null || !isInputPin(pin)) {
                System.err.println("input pin missing: " + name);
                return 2;
            }
        }
        for (String name : outputs) {
            Component pin = pins.get(name);
            if (pin != null && isInputPin(pin)) {
                System.err.println("output is an input pin: " + name);
                return 2;
            }
            if (!readable.containsKey(name)) {
                System.err.println("output pin or LED missing: " + name);
                return 2;
            }
        }
        loaded.propagator.propagate();

        int passed = 0;
        int failed = 0;
        int row = 0;
        BufferedReader reader = new BufferedReader(new InputStreamReader(System.in));
        String line;
        while ((line = reader.readLine()) != null) {
            line = line.trim();
            if (line.isEmpty() || line.startsWith("#")) {
                continue;
            }
            String[] cells = line.split("\\s+");
            int expected = inputs.length + outputs.length;
            if (cells.length < expected) {
                System.err.println("row " + row + " has " + cells.length + " values, want " + expected);
                return 2;
            }
            try {
            for (int i = 0; i < inputs.length; i++) {
                if (TICK.equals(inputs[i])) {
                    continue;
                }
                Component pin = pins.get(inputs[i]);
                Long value = parseNumber(cells[i], widthOf(pin), false);
                if (value == null) {
                    System.err.println("row " + row + ": bad value: " + cells[i]);
                    return 2;
                }
                drive(loaded.state, pin, value);
            }
            loaded.propagator.propagate();
            for (int i = 0; i < inputs.length; i++) {
                if (!TICK.equals(inputs[i])) {
                    continue;
                }
                int cycles = Integer.parseInt(cells[i]);
                for (int n = 0; n < cycles; n++) {
                    loaded.propagator.toggleClocks();
                    loaded.propagator.propagate();
                    loaded.propagator.toggleClocks();
                    loaded.propagator.propagate();
                }
            }
            boolean rowOk = true;
            for (int i = 0; i < outputs.length; i++) {
                Component probe = readable.get(outputs[i]);
                String cell = cells[inputs.length + i];
                Long want = parseNumber(cell, widthOf(probe), true);
                if (want == null) {
                    continue;
                }
                Value got = read(loaded.state, probe);
                boolean ok = got != null && got.isFullyDefined() && got.toLongValue() == want;
                if (!ok) {
                    rowOk = false;
                    System.out.println(
                        "FAIL row " + row + " " + outputs[i]
                            + " expected " + want + " got " + got);
                }
            }
            if (rowOk) {
                passed++;
            } else {
                failed++;
            }
            } catch (IllegalArgumentException ex) {
                System.err.println("row " + row + ": " + ex.getMessage());
                return 2;
            }
            row++;
        }
        System.out.println("PASSED=" + passed);
        System.out.println("FAILED=" + failed);
        return failed == 0 ? 0 : 1;
    }

    /** Decimal, {@code 0x} hex, or {@code 0b} binary. Don't-care is null when allowed. */
    static Long parseNumber(String text, int width, boolean allowDontCare) {
        String raw = text.trim();
        if (allowDontCare && (raw.equalsIgnoreCase("x") || raw.equals("-") || raw.equalsIgnoreCase("<DC>"))) {
            return null;
        }
        int radix = 10;
        String digits = raw;
        if (raw.startsWith("0x") || raw.startsWith("0X")) {
            radix = 16;
            digits = raw.substring(2);
        } else if (raw.startsWith("0b") || raw.startsWith("0B")) {
            radix = 2;
            digits = raw.substring(2);
        }
        if (digits.isEmpty()) {
            throw new IllegalArgumentException("bad value: " + text);
        }
        long value;
        try {
            value = Long.parseUnsignedLong(digits, radix);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("bad value: " + text);
        }
        if (width < 64) {
            long limit = 1L << width;
            if (Long.compareUnsigned(value, limit) >= 0) {
                throw new IllegalArgumentException(
                    "value " + text + " does not fit in " + width + " bits");
            }
        }
        return value;
    }

    static final class Loaded {
        final Circuit circuit;
        final CircuitState state;
        final Propagator propagator;

        Loaded(Circuit circuit, CircuitState state, Propagator propagator) {
            this.circuit = circuit;
            this.state = state;
            this.propagator = propagator;
        }
    }

    static Loaded open(String circPath, String circuitName) throws Exception {
        LogisimFile file = new QuietLoader().openLogisimFile(new File(circPath));
        Project project = new Project(file);
        Circuit circuit = file.getCircuit(circuitName);
        if (circuit == null) {
            throw new IllegalArgumentException("circuit not found: " + circuitName);
        }
        CircuitState state = CircuitState.createRootState(project, circuit, Thread.currentThread());
        return new Loaded(circuit, state, state.getPropagator());
    }

    static String labelOf(Component comp) {
        AttributeSet attrs = comp.getAttributeSet();
        if (!attrs.containsAttribute(StdAttr.LABEL)) {
            return "";
        }
        Object value = attrs.getValue(StdAttr.LABEL);
        return value == null ? "" : value.toString();
    }

    static boolean isInputPin(Component comp) {
        AttributeSet attrs = comp.getAttributeSet();
        if (!attrs.containsAttribute(Pin.ATTR_TYPE)) {
            return true;
        }
        return Pin.INPUT.equals(attrs.getValue(Pin.ATTR_TYPE));
    }

    static int widthOf(Component comp) {
        AttributeSet attrs = comp.getAttributeSet();
        if (!attrs.containsAttribute(StdAttr.WIDTH)) {
            return 1;
        }
        Object value = attrs.getValue(StdAttr.WIDTH);
        if (value instanceof BitWidth) {
            return ((BitWidth) value).getWidth();
        }
        return 1;
    }

    static void drive(CircuitState state, Component pin, long value) {
        InstanceState ist = state.getInstanceState(pin);
        ((Pin) pin.getFactory()).driveInputPin(ist, Value.createKnown(BitWidth.create(widthOf(pin)), value));
        pin.propagate(state);
    }

    static Value read(CircuitState state, Component comp) {
        return state.getValue(comp.getEnd(0).getLocation());
    }
}
