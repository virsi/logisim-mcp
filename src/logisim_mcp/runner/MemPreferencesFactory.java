// In-memory java.util.prefs backend. Logisim 5.0.0 touches the Windows
// registry from AppPreferences during class init; a sandbox that denies
// HKCU\Software\JavaSoft\Prefs crashes before main can run. Pass
// -Djava.util.prefs.PreferencesFactory=MemPreferencesFactory on Windows.

import java.util.HashMap;
import java.util.Map;
import java.util.prefs.AbstractPreferences;
import java.util.prefs.Preferences;
import java.util.prefs.PreferencesFactory;

public final class MemPreferencesFactory implements PreferencesFactory {
    private final Preferences userRoot = new MemNode(null, "");
    private final Preferences systemRoot = new MemNode(null, "");

    @Override
    public Preferences systemRoot() {
        return systemRoot;
    }

    @Override
    public Preferences userRoot() {
        return userRoot;
    }

    static final class MemNode extends AbstractPreferences {
        private final Map<String, String> values = new HashMap<>();
        private final Map<String, MemNode> children = new HashMap<>();

        MemNode(AbstractPreferences parent, String name) {
            super(parent, name);
        }

        @Override
        protected void putSpi(String key, String value) {
            values.put(key, value);
        }

        @Override
        protected String getSpi(String key) {
            return values.get(key);
        }

        @Override
        protected void removeSpi(String key) {
            values.remove(key);
        }

        @Override
        protected void removeNodeSpi() {
            values.clear();
        }

        @Override
        protected String[] keysSpi() {
            return values.keySet().toArray(new String[0]);
        }

        @Override
        protected String[] childrenNamesSpi() {
            return children.keySet().toArray(new String[0]);
        }

        @Override
        protected AbstractPreferences childSpi(String name) {
            return children.computeIfAbsent(name, child -> new MemNode(this, child));
        }

        @Override
        protected void syncSpi() {}

        @Override
        protected void flushSpi() {}
    }
}
