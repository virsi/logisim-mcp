// EXPERIMENTAL — partially working sequential test runner.
//
// Demonstrates the approach: open a .circ headless, drive input pins
// programmatically, ask the Simulator to propagate, read output pins.
// The current implementation does NOT reliably observe edge-triggered
// updates on Register/Counter because Logisim 4.0.0's Simulator
// expects a Swing event-dispatch thread (Propagator.propagate must run
// on its own propagation thread). A future version should either
// drive Propagator directly via Simulator's internal Runnable queue
// or run Logisim with `-Djava.awt.headless=false` and a virtual frame
// buffer.
//
// CLI:
//   java -cp logisim-evolution.jar:. SeqTester <circ> <circuit> <inputs> <outputs>
// stdin: one row per line with input values followed by expected
// output values; output: PASSED= / FAILED= counts plus FAIL lines.

import com.cburch.logisim.file.Loader;
import com.cburch.logisim.file.LogisimFile;
import com.cburch.logisim.proj.Project;
import com.cburch.logisim.circuit.Circuit;
import com.cburch.logisim.circuit.CircuitState;
import com.cburch.logisim.circuit.Simulator;
import com.cburch.logisim.comp.Component;
import com.cburch.logisim.std.wiring.Pin;
import com.cburch.logisim.instance.Instance;
import com.cburch.logisim.instance.InstanceState;
import com.cburch.logisim.instance.StdAttr;
import com.cburch.logisim.data.Value;
import com.cburch.logisim.data.BitWidth;

import java.io.BufferedReader;
import java.io.File;
import java.io.InputStreamReader;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class SeqTester {

    public static void main(String[] args) throws Exception {
        if (args.length < 4) {
            System.err.println("usage: SeqTester <circ> <circuit> <in0,in1,..> <out0,out1,..>");
            System.exit(2);
        }
        File circFile = new File(args[0]);
        String circuitName = args[1];
        String[] inputs = args[2].split(",");
        String[] outputs = args[3].split(",");

        Loader loader = new Loader(null);
        LogisimFile lf = loader.openLogisimFile(circFile);
        Project project = new Project(lf);
        Circuit circuit = lf.getCircuit(circuitName);
        if (circuit == null) {
            System.err.println("circuit not found: " + circuitName);
            System.exit(2);
        }
        project.setCurrentCircuit(circuit);
        CircuitState state = project.getCircuitState();
        Simulator sim = project.getSimulator();
        sim.setAutoPropagation(true);
        sim.reset();
        Thread.sleep(100);

        Map<String, Instance> pinByLabel = new HashMap<>();
        for (Component comp : circuit.getNonWires()) {
            if (!(comp.getFactory() instanceof Pin)) continue;
            Instance inst = Instance.getInstanceFor(comp);
            if (inst == null) continue;
            String label = inst.getAttributeValue(StdAttr.LABEL);
            if (label != null && !label.isEmpty()) pinByLabel.put(label, inst);
        }

        for (String name : inputs) {
            if (!pinByLabel.containsKey(name)) {
                System.err.println("input pin missing: " + name);
                System.exit(2);
            }
        }
        for (String name : outputs) {
            if (!pinByLabel.containsKey(name)) {
                System.err.println("output pin missing: " + name);
                System.exit(2);
            }
        }

        BufferedReader br = new BufferedReader(new InputStreamReader(System.in));
        int passed = 0, failed = 0, rowIdx = 0;
        List<String> failures = new ArrayList<>();
        String line;
        while ((line = br.readLine()) != null) {
            String trimmed = line.trim();
            if (trimmed.isEmpty() || trimmed.startsWith("#")) continue;
            rowIdx++;
            String[] tokens = trimmed.split("\\s+");
            int expectedCols = inputs.length + outputs.length;
            if (tokens.length != expectedCols) {
                System.err.println("row " + rowIdx + ": got " + tokens.length
                    + " tokens, expected " + expectedCols);
                System.exit(2);
            }

            for (int i = 0; i < inputs.length; i++) {
                Instance pin = pinByLabel.get(inputs[i]);
                BitWidth w = pin.getAttributeValue(StdAttr.WIDTH);
                long v = parseLong(tokens[i]);
                InstanceState ist = state.getInstanceState(pin);
                ((Pin) pin.getFactory()).driveInputPin(
                    ist, Value.createKnown(w, v));
            }

            // With auto-propagation on, the simulator picks up driveInputPin
            // changes asynchronously. Kick it explicitly and give it time.
            for (int k = 0; k < 10; k++) {
                sim.step();
                Thread.sleep(20);
            }
            sim.nudge();
            Thread.sleep(200);

            StringBuilder mismatch = new StringBuilder();
            for (int i = 0; i < outputs.length; i++) {
                Instance pin = pinByLabel.get(outputs[i]);
                BitWidth w = pin.getAttributeValue(StdAttr.WIDTH);
                long expected = parseLong(tokens[inputs.length + i]);
                long mask = w.getWidth() >= 64 ? -1L : ((1L << w.getWidth()) - 1L);
                InstanceState ist = state.getInstanceState(pin);
                Value v = ((Pin) pin.getFactory()).getValue(ist);
                long actual = v.toLongValue() & mask;
                expected &= mask;
                if (actual != expected) {
                    mismatch.append(" ").append(outputs[i])
                        .append("=").append(actual)
                        .append("(exp ").append(expected).append(")");
                }
            }
            if (mismatch.length() == 0) {
                passed++;
            } else {
                failed++;
                failures.add("FAIL row=" + rowIdx + mismatch);
            }
        }

        System.out.println("PASSED=" + passed);
        System.out.println("FAILED=" + failed);
        for (String f : failures) System.out.println(f);
        System.exit(failed == 0 ? 0 : 1);
    }

    private static long parseLong(String s) {
        s = s.trim();
        if (s.equalsIgnoreCase("x") || s.equals("-") || s.equals("<DC>")) return 0L;
        if (s.startsWith("0x") || s.startsWith("0X")) return Long.parseLong(s.substring(2), 16);
        if (s.startsWith("0b") || s.startsWith("0B")) return Long.parseLong(s.substring(2), 2);
        return Long.parseLong(s);
    }
}
