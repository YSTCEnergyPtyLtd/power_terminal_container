package main.java.method;

import com.fasterxml.jackson.databind.ObjectMapper;
import main.java.model.Device;
import main.java.model.Result;
import main.java.model.Station;
import main.java.dataOp.DataProcess;
import java.util.ArrayList;
import java.util.Random;

public class MainMethod {

    public static void main(String[] args) throws Exception {

        String devicesJson = args[0];
        ObjectMapper mapper = new ObjectMapper();
        ArrayList<Device> devices = mapper.readValue(
                devicesJson,
                mapper.getTypeFactory().constructCollectionType(ArrayList.class, Device.class)
        );

        if (devices == null || devices.isEmpty()) {
            throw new IllegalArgumentException("devices列表为空！");
        }

        Random rad = new Random();
        Station station = DataProcess.getStation(rad);

        Result result = AU_SmartGrid_Game.getResult(station, devices, rad);

        System.out.println(mapper.writeValueAsString(result));
    }
}